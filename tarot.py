import asyncio
import json
import logging
import math
import random
import re
from pathlib import Path

import emoji
from PIL import Image

from tarot_config import (
    ALL_ZODIAC_KEYS,
    BUSY_TIPS,
    COMPLETE_TEXT_TIPS,
    DEFAULT_SPREAD_KEY,
    ERROR_TIP,
    MAJOR_ARCANA_MAX_ID,
    MAX_LENGTH,
    NAME_SUFFIXES,
    NONE_TEXT_TIPS,
    REPLACE_STRING_TO_EMPTY,
    RESOURCES_DIR,
    TAROT_API_KEY,
    TAROT_DATA_PATH,
    TAROT_MASTER_CONTENT,
    TAROT_MODEL,
    TAROT_PROVIDER,
    TAROT_SPREADS,
    TAROT_URL,
    TOO_LONG_TIP,
    USER_RA_MSG,
)
from llm_client import create_chat_client

DEFAULT_CONNECT_URL = TAROT_URL

logger = logging.getLogger(__name__)


def filter_card_keys(cards: dict, card_select: int = 0) -> list[str]:
    if card_select == 1:
        return [key for key, card in cards.items() if card.get("id", 0) <= MAJOR_ARCANA_MAX_ID]
    if card_select == 2:
        return [key for key, card in cards.items() if card.get("id", 0) > MAJOR_ARCANA_MAX_ID]
    return list(cards.keys())


def resolve_card_elements(card: dict) -> list[tuple[str, str, str]]:
    pairs = []
    if card.get("first_element"):
        pairs.append(("第一元素", card.get("first_element_cn") or card["first_element"], card["first_element"]))
    if card.get("second_element"):
        pairs.append(("第二元素", card.get("second_element_cn") or card["second_element"], card["second_element"]))
    return pairs


def extract_spread_key(raw: str, spreads: dict, default: str) -> str:
    text = (raw or "").strip()
    compact = TarotUtils.keep_english_digits(text)
    hits = [
        key for key in spreads
        if key.lower() in text.lower() or key.lower() in compact.lower()
    ]
    if hits:
        return max(hits, key=len)
    if compact in spreads:
        return compact
    return default


def _spread_name_stem(name_cn: str) -> str:
    stem = name_cn or ""
    for suffix in NAME_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem


def pick_spread_by_keywords(message: str, spreads: dict, min_score: int = 2) -> str | None:
    ranked: list[tuple[int, str]] = []
    for key, info in spreads.items():
        score = 0
        tags = list(info.get("suitable_for_cn") or []) + list(info.get("suitable_for") or [])
        for tag in tags:
            if tag and tag in message:
                score += 2 + len(tag)
        name_cn = info.get("name_cn") or ""
        if name_cn and name_cn in message:
            score += 10
        stem = _spread_name_stem(name_cn)
        if stem and stem in message:
            score += 8 + len(stem)
        desc = info.get("description_cn") or ""
        if desc and desc in message:
            score += 4
        if score:
            ranked.append((score, key))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1]))
    if ranked[0][0] < min_score:
        return None
    if len(ranked) == 1 or ranked[0][0] > ranked[1][0]:
        return ranked[0][1]
    return None


def build_interpret_messages(persona: str, context: str, user_message: str) -> list[dict]:
    return [
        {"role": "system", "content": f"{persona}\n\n{context}".strip()},
        {"role": "user", "content": USER_RA_MSG + user_message},
    ]


def split_result_texts(text: str) -> list[str]:
    cleaned = TarotUtils.replace_string((text or "").strip())
    result = []
    for part in re.split(r"[\n。]", cleaned):
        hand = part.strip().strip("。,，.").lstrip("？?!！").strip()
        hand = TarotUtils.strip_leading_fillers(hand)
        if hand:
            result.append(hand)
    return result


class TarotContent:
    def __init__(
        self,
        failure_tips: str = None,
        complete_text: str = None,
        result_texts: list[str] = None,
        tarot_text: str = None,
        tarot_info: dict = None,
        is_complete: bool = False,
    ):
        self.result_texts: list[str] = result_texts
        self.failure_text = failure_tips
        self.tarot_text = tarot_text
        self.complete_text = complete_text
        self.is_complete: bool = is_complete
        self.tarot_info: dict = tarot_info


class TarotUtils:
    @staticmethod
    def clean_redundant_punctuation(text: str):
        return re.sub(r"(([？?！!。.，,]))[，,。.！!？?…、]+", r"\1", text)

    @staticmethod
    def remove_emojis(text: str):
        result_text = emoji.demojize(text)
        pattern = r":[a-z]+[_*[a-z]*]*[-*[a-z]*[_*[a-z]*]*]*:"
        for match in re.findall(pattern, result_text):
            result_text = result_text.replace(match, "")
        return result_text

    @staticmethod
    def strip_leading_fillers(text: str) -> str:
        stripped = (text or "").lstrip()
        for filler in sorted(REPLACE_STRING_TO_EMPTY, key=len, reverse=True):
            if stripped.startswith(filler):
                return stripped[len(filler):].lstrip("，,、;； ")
        return text or ""

    @staticmethod
    def replace_string(msg: str):
        result = TarotUtils.strip_leading_fillers(msg)
        return TarotUtils.clean_redundant_punctuation(result)

    @staticmethod
    def keep_english_digits(text):
        return re.sub(r"[^a-zA-Z0-9]", "", text)


class TarotDraw:
    def __init__(self, tarot_dir: str | Path | None = None):
        self.tarot_dir = Path(tarot_dir) if tarot_dir is not None else RESOURCES_DIR

    def compose(self, cards: list[dict], spread: dict, is_reversed_list: list) -> Image.Image:
        base_img = Image.open(self.tarot_dir / "wallpaper.png").convert("RGBA")
        card_dir = self.tarot_dir / "cards"
        processed = []
        for index, args in enumerate(spread["draw"]):
            card_path = card_dir / f"{cards[index]['id']}.jpg"
            processed.append(self._process_card(card_path, args, is_reversed_list[index]))
        for card_img, position in processed:
            base_img.alpha_composite(card_img, dest=position)
        return base_img

    async def draw(self, cards: list[dict], spread: dict, is_reversed_list: list) -> Image.Image:
        return await asyncio.to_thread(self.compose, cards, spread, is_reversed_list)

    def _process_card(self, card_path: Path, args: dict, is_reversed: bool) -> tuple:
        card_img = Image.open(card_path).convert("RGBA")
        position_args = args["position"]
        rotate = args["rotate"]
        scale = args["scale"]

        if is_reversed:
            card_img = card_img.rotate(180, expand=True, resample=Image.Resampling.BICUBIC)
        if not math.isclose(rotate, 0.0):
            card_img = card_img.rotate(rotate, expand=True, resample=Image.Resampling.BICUBIC)
        if not math.isclose(scale, 1.0):
            new_size = (int(card_img.width * scale), int(card_img.height * scale))
            resample = Image.Resampling.LANCZOS if scale < 1.0 else Image.Resampling.BICUBIC
            card_img = card_img.resize(new_size, resample=resample)

        position = (int(position_args[0] - card_img.width / 2), int(position_args[1] - card_img.height / 2))
        return (card_img, position)


class Tarot:
    def __init__(
        self,
        model: str | None = None,
        url: str | None = None,
        api_key: str | None = None,
        provider: str | None = None,
    ):
        self._lock = asyncio.Lock()
        self.tarot_data = None
        self.reload_tarot()
        self.model = model or TAROT_MODEL
        self.provider = provider or TAROT_PROVIDER
        self.client = create_chat_client(self.provider, url or TAROT_URL, api_key or TAROT_API_KEY)

    @property
    def is_busy(self) -> bool:
        return self._lock.locked()

    def reload_tarot(self):
        with open(TAROT_DATA_PATH, "r", encoding="utf-8") as file:
            self.tarot_data = json.load(file)

    def update_client(
        self,
        model: str | None = None,
        url: str | None = None,
        api_key: str | None = None,
        provider: str | None = None,
    ):
        self.model = model or self.model
        self.provider = provider or self.provider
        self.client = create_chat_client(
            self.provider,
            url or TAROT_URL,
            api_key if api_key is not None else TAROT_API_KEY,
        )

    reloadTarot = reload_tarot
    updateClient = update_client

    def _handle_element_text(self, element, a_mod: bool = False, total_zodiacs_key: set = None):
        if total_zodiacs_key is None:
            total_zodiacs_key = set()

        result_text = (
            f"元素:{element['name_cn']},能量属性:{element['genderCN']},"
            f"颜色:{', '.join(element['colorsCN'])},生物:{element['animals']},"
            f"表达:{element['expression']},属性:{element['attribute']},含义:{element['meaning']}"
        )
        if a_mod:
            total_zodiacs_key.update(element["zodiac"])
            result_text += f",元素对应星座:{', '.join(element['zodiacCN'])}"
        return result_text

    def _match_court(self, card_key: str):
        court_map = self.tarot_data["courtElementalCorrespondence"]
        lowered = card_key.lower()
        for court_key, info in court_map.items():
            if lowered.startswith(court_key):
                return court_key, info
        return None, None

    async def select_spreads(self, message: str):
        spreads = self.tarot_data["spreads"]
        by_keywords = pick_spread_by_keywords(message, spreads)
        if by_keywords:
            logger.info("spread picked by keywords: %s", by_keywords)
            return by_keywords

        spreads_text = "可选的牌阵有:"
        for spread_id, info in spreads.items():
            tags = ",".join(info.get("suitable_for_cn") or [])
            spreads_text += f"\n{spread_id}: {info['name_cn']} [{tags}]"

        messages = [
            {"role": "system", "content": TAROT_SPREADS + spreads_text},
            {"role": "user", "content": message},
        ]
        response = await self.client.chat(model=self.model, messages=messages)
        out_spread_key = extract_spread_key(
            response["message"]["content"],
            spreads,
            DEFAULT_SPREAD_KEY,
        )
        logger.info("spread picked by model: %s", out_spread_key)
        return out_spread_key

    def _pack_tarot_info(
        self,
        spread_key,
        card_keys,
        elem_keys,
        court_elem_corr_keys,
        ast_mod_keys,
        zodiacs_keys,
        is_reversed_list,
    ):
        datas = {
            "spread": self.tarot_data["spreads"][spread_key],
            "cards": {},
            "is_reversed_list": is_reversed_list,
            "astrologyModality": {},
            "courtElementalCorrespondence": {},
            "zodiacs": {},
            "elements": {},
        }
        for card_key in card_keys:
            datas["cards"][card_key] = self.tarot_data["cards"][card_key]
        for elem_key in elem_keys:
            datas["elements"][elem_key] = self.tarot_data["elements"][elem_key]
        for court_key in court_elem_corr_keys:
            datas["courtElementalCorrespondence"][court_key] = self.tarot_data["courtElementalCorrespondence"][court_key]
        for ast_key in ast_mod_keys:
            datas["astrologyModality"][ast_key] = self.tarot_data["astrologyModality"][ast_key]
        for zodiac_key in zodiacs_keys:
            datas["zodiacs"][zodiac_key] = self.tarot_data["zodiacs"][zodiac_key]
        return datas

    def _build_astrology_text(self, zodiac_keys: set) -> tuple[str, set]:
        if not zodiac_keys:
            return "", set()
        if "all" in zodiac_keys:
            zodiac_keys = set(ALL_ZODIAC_KEYS)

        zodiacs = self.tarot_data["zodiacs"]
        astrology_modality = self.tarot_data["astrologyModality"]
        modality_keys = set()
        zodiacs_text_info = ""
        for zodiac_key in zodiac_keys:
            zodiac = zodiacs[zodiac_key]
            modality_keys.add(zodiac["astrologyModality"])
            zodiacs_text_info += (
                f"\n{zodiac['zodiacCN']}: {zodiac['astrologyModalityCN']}"
                f"\n元素:{zodiac['elementCN']},季节:{zodiac['seasonCN']},本质:{zodiac['nature']}"
            )
            if zodiac["rulingBodyTraditional"]:
                zodiacs_text_info += (
                    f",现代守护星: {zodiac['rulingBodyModern']}, 古典守护星: {zodiac['rulingBodyTraditional']}"
                )
            else:
                zodiacs_text_info += f",守护星: {zodiac['rulingBodyModern']}"

        modality_info = ""
        for modality_key in modality_keys:
            value = astrology_modality[modality_key]
            modality_info += (
                f"\n{value['name_cn']},对应宫廷牌:{value['cardCN']},"
                f"属性:{value['attribute']},含义:{value['meaning']}"
            )
        return "占星讯息:" + modality_info + zodiacs_text_info, modality_keys

    def _build_spread_context(self, spread, drawn_keys, is_reversed_list, a_mod: bool):
        cards = self.tarot_data["cards"]
        elements = self.tarot_data["elements"]
        positions = spread["positions"]

        tarot_texts = f"塔罗牌阵讯息:\n{spread['name_cn']}: {spread['description_cn']}\n"
        show_text = f"{spread['name_cn']}: {spread['description_cn']}"
        total_elements = set()
        total_zodiacs = set()
        court_keys = set()

        for index, position in enumerate(positions):
            card_key = drawn_keys[index]
            card = cards[card_key]
            reversed_card = is_reversed_list[index]
            card_name = ("逆" if reversed_card else "正") + card["card_name_cn"]
            card_description = card["reversed_cn"] if reversed_card else card["upright_cn"]

            tarot_texts += f"\n{index + 1}. {position['name_cn']}: {position['description_cn']}"
            tarot_texts += f"\n{card_name}: {card_description}"
            show_text += f"\n#{index + 1} {position['name_cn']}: {position['description_cn']}\n{card_name}"

            for label, name_cn, element_key in resolve_card_elements(card):
                total_elements.add(element_key)
                tarot_texts += (
                    f"\n{label}:{name_cn},"
                    + self._handle_element_text(elements[element_key], a_mod, total_zodiacs)
                )

            court_key, court_elemental = self._match_court(card_key)
            if court_elemental:
                court_keys.add(court_key)
                court_element = court_elemental["element"]
                total_elements.add(court_element)
                tarot_texts += (
                    f"\n宫廷元素:{court_elemental['elementCN']},"
                    f"{court_elemental['nameCN']}含义:{court_elemental['meaning']},"
                    + self._handle_element_text(elements[court_element], a_mod, total_zodiacs)
                )

        tarot_texts += f"\n阵型解释:{spread['interpretation_method_cn']}"
        return tarot_texts, show_text, total_elements, total_zodiacs, court_keys

    def _busy_result(self) -> TarotContent:
        result = TarotContent()
        result.failure_text = random.choice(BUSY_TIPS)
        return result

    async def divination(
        self,
        user_message: str,
        a_mod: bool = False,
        is_busy: bool = None,
        card_select: int = 0,
    ) -> TarotContent:
        if is_busy or self._lock.locked():
            return self._busy_result()

        async with self._lock:
            return await self._divination_unlocked(user_message, a_mod, card_select)

    async def _divination_unlocked(self, user_message: str, a_mod: bool, card_select: int) -> TarotContent:
        result = TarotContent()
        try:
            user_message = TarotUtils.remove_emojis(user_message)
            if len(user_message) <= 0:
                result.failure_text = random.choice(NONE_TEXT_TIPS)
                return result
            if len(user_message) > MAX_LENGTH:
                result.failure_text = TOO_LONG_TIP
                return result

            spread_key = await self.select_spreads(user_message)
            spread = self.tarot_data["spreads"][spread_key]
            card_count = len(spread["positions"])
            deck_keys = filter_card_keys(self.tarot_data["cards"], card_select)
            drawn_keys = random.sample(deck_keys, card_count)
            is_reversed_list = [random.choice([True, False]) for _ in range(card_count)]

<<<<<<< HEAD
            tarot_texts, show_text, total_elements, total_zodiacs, court_keys = self._build_spread_context(
                spread, drawn_keys, is_reversed_list, a_mod
=======
            random_cards = random.sample(tarot_cards_keys, card_count)
            
            # 塔罗
            tarot_texts = f"塔罗牌阵讯息:\n{spread_name}: {spread_description}\n"
            
            show_text = f"{spread_name}: {spread_description}"
            
            total_court_elemental_correspondence_keys = set()
            total_elements = set()
            total_zodiacs_key = set()
            
            for index, card in enumerate(spread_positions):
                name_cn = card["name_cn"]
                description_cn = card["description_cn"]
                tarot_texts += f"\n{index + 1}. {name_cn}: {description_cn}"
                tarot_card_key = random_cards[index] # 塔罗牌索引
                tarot_card = tarot_cards[tarot_card_key] # 塔罗牌
                is_reversed = random.choice([True, False]) # 是否为逆位
                is_reversed_list.append(is_reversed)
                card_name = tarot_card["card_name_cn"] # 塔罗牌名字
                card_id = tarot_card["id"]


                # 第一元素
                first_element = tarot_card["first_element"]
                # 第二元素
                second_element = tarot_card["second_element"]
                # 宫廷元素
                court_elemental = None

                court_elemental_correspondence_keys = court_elemental_correspondence.keys()
                
                for court_elemental_correspondence_key in court_elemental_correspondence_keys:
                    total_court_elemental_correspondence_keys.add(court_elemental_correspondence_key)
                    # 宫廷牌属性
                    if tarot_card_key.lower().startswith(court_elemental_correspondence_key):
                        court_elemental = court_elemental_correspondence[court_elemental_correspondence_key]

                card_description = ""

                if is_reversed: # 逆位
                    card_description = tarot_card["reversed_cn"]
                    card_name = "逆" + card_name
                else: # 正位
                    card_description = tarot_card["upright_cn"]
                    card_name = "正" + card_name
                
                show_text += f"\n#{index + 1} {name_cn}: {description_cn}\n{card_name}"
                tarot_texts += f"\n{card_name}: {card_description}"
                
                if first_element:
                    first_element_cn = tarot_card["first_element_cn"]
                    total_elements.add(first_element)
                    element = elements[first_element]
                    tarot_texts += f"\n第一元素:{first_element_cn}," + self.__handle_element_text(element, a_mod, total_zodiacs_key)
                if second_element:
                    second_element_cn = tarot_card["second_element_cn"]
                    total_elements.add(second_element)
                    element = elements[second_element]
                    tarot_texts += f"\n第二元素:{second_element_cn}," + self.__handle_element_text(element, a_mod, total_zodiacs_key)
                if court_elemental:
                    court_name = court_elemental["nameCN"]
                    court_element = court_elemental["element"]
                    court_element_cn = court_elemental["elementCN"]
                    court_meaning = court_elemental["meaning"]
                    total_elements.add(court_element)
                    element = elements[court_element]
                    tarot_texts += f"\n宫廷元素:{court_element_cn},{court_name}含义:{court_meaning}," + self.__handle_element_text(element, a_mod, total_zodiacs_key)
            
            spread_interpretation = spread["interpretation_method_cn"]
            tarot_texts += f"\n阵型解释:{spread_interpretation}"
            
            if "all" in total_zodiacs_key and a_mod:
                total_zodiacs_key = {"Aries", "Leo", "Sagittarius", "Taurus","Virgo","Capricorn", "Gemini","Libra","Aquarius", "Cancer","Scorpio","Pisces"}
            
            # 占星
            zodiacs_text = ""
            
            total_astrology_modality_keys = set()
            
            
            if a_mod:
                zodiacs_text = "占星讯息:"
                zodiacs_text_info = ""
                for zodiacs_key in total_zodiacs_key:
                    zodiac = zodiacs[zodiacs_key]
                    astrology_modality_key = zodiac['astrologyModality'] # 占星模式
                    total_astrology_modality_keys.add(astrology_modality_key)
                    
                    zodiac_name = zodiac['zodiacCN'] # 星座名称
                    astrology_modality_cn = zodiac['astrologyModalityCN'] # 占星模式cn
                    element_cn = zodiac['elementCN'] # 元素
                    season_cn = zodiac['seasonCN'] # 季节
                    nature = zodiac['nature'] # 本质 
                    ruling_body_modern = zodiac['rulingBodyModern'] # 现代守护星
                    ruling_body_traditional = zodiac['rulingBodyTraditional'] # 古典守护星
                    
                    zodiacs_text_info += f"\n{zodiac_name}: {astrology_modality_cn}\n元素:{element_cn},季节:{season_cn},本质:{nature}"
                    
                    if ruling_body_traditional:
                        zodiacs_text_info += f",现代守护星: {ruling_body_modern}, 古典守护星: {ruling_body_traditional}"
                    else:
                        zodiacs_text_info += f",守护星: {ruling_body_modern}"
                
                astrology_modality_info = ""
                for total_astrology_modality_key in total_astrology_modality_keys:
                    astrology_modality_value = astrology_modality[total_astrology_modality_key]
                    name_cn = astrology_modality_value["name_cn"] # 占星模式cn
                    card = astrology_modality_value["cardCN"] # 对应宫廷牌
                    attribute = astrology_modality_value["attribute"] # 属性
                    meaning = astrology_modality_value["meaning"] # 含义
                    
                    astrology_modality_info += f"\n{name_cn},对应宫廷牌:{card},属性:{attribute},含义:{meaning}"
                
                zodiacs_text += astrology_modality_info + zodiacs_text_info
            
            messages = [
                {
                    "role": "system",
                    "content": TAROT_MASTER_CONTENT(a_mod), # 系统提示词
                },
                {
                
                    "role": "user",
                    "content": USER_VL_MSG + user_message
                }
            ]
            
            messages.append({
                    "role": "assistant",
                    "content": zodiacs_text # 占星讯息
            })
            
            messages.extend([{
                    "role": "assistant",
                    "content": tarot_texts # 塔罗牌讯息
                },
                {
                
                    "role": "user",
                    "content": USER_RA_MSG + user_message
                }]
>>>>>>> ef872432feddde1906cb2a63cb79720578d9fe85
            )

            zodiacs_text = ""
            modality_keys = set()
            if a_mod:
                zodiacs_text, modality_keys = self._build_astrology_text(total_zodiacs)

            context = tarot_texts if not zodiacs_text else f"{zodiacs_text}\n\n{tarot_texts}"
            messages = build_interpret_messages(TAROT_MASTER_CONTENT(a_mod), context, user_message)
            response = await self.client.chat(model=self.model, messages=messages)

            result.result_texts = split_result_texts(response["message"]["content"])
            result.tarot_text = show_text
            result.is_complete = True
            result.complete_text = random.choice(COMPLETE_TEXT_TIPS)
            result.tarot_info = self._pack_tarot_info(
                spread_key,
                drawn_keys,
                total_elements,
                court_keys,
                modality_keys,
                total_zodiacs if a_mod else set(),
                is_reversed_list,
            )
        except Exception:
            logger.exception("divination failed")
            result.failure_text = ERROR_TIP
        return result
