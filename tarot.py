import json, re, random, math, asyncio
from tarot_config import *
import emoji, ollama
from PIL import Image

DEFAULT_CONNECT_URL = "localhost:11434"

class TarotContent:
    def __init__(self, failure_tips: str = None, complete_text: str = None, result_texts: list[str] = None, tarot_text: str = None, tarot_info: dict = None, is_complete: bool = False):
        self.result_texts: list[str] = result_texts
        self.failure_text = failure_tips
        self.tarot_text = tarot_text
        self.complete_text = complete_text
        self.is_complete: bool = is_complete
        self.tarot_info: dict = tarot_info

class TarotUtils:
    @staticmethod
    def clean_redundant_punctuation(text: str):
        # 规则：匹配【？、！、，】后面连续出现的标点，并只保留第一个标点
        text = re.sub(r'(([？?！!。.，,]))[，,。.！!？?…、]+', r'\1', text)
        return text
    
    @staticmethod
    def remove_emojis(text : str):
        # 把emoji变成字符串形式 比如🌈变成:rainbow:
        result_text = emoji.demojize(text)
        
        # 设置规则,匹配string里的":xxx:"
        pattern = r":[a-z]+[_*[a-z]*]*[-*[a-z]*[_*[a-z]*]*]*:"
        matches = re.findall(pattern, result_text)
        
        # 去除emoji
        for matche in matches:
            result_text = result_text.replace(matche, "")
            
        return result_text

    @staticmethod
    def replace_string(msg: str):
        result: str = msg
        for string in REPLACE_STRING_TO_EMPTY:
            result = result.replace(string, "")
            
        result = TarotUtils.clean_redundant_punctuation(result)
        return result

    @staticmethod
    def keep_english_digits(text):
        # 匹配非英文、非数字的字符并替换为空字符串
        return re.sub(r'[^a-zA-Z0-9]', '', text)

class TarotDraw:
    def __init__(self, tarot_dir: str):
        self.tarot_dir: str = tarot_dir

    async def draw(self, cards: list[dict], spread: dict, is_reversed_list: list) -> Image:
        wallpaper_path = f"{self.tarot_dir}/wallpaper.png"
        
        base_img = Image.open(wallpaper_path).convert("RGBA")
        
        card_dir = f"{self.tarot_dir}/cards"
        
        # Process cards concurrently
        card_tasks = []
        
        for index, args in enumerate(spread["draw"]):
            card = cards[index]
            card_id = card["id"]
            card_path = f"{card_dir}/{card_id}.jpg"
            task = self._process_card(card_path, args, is_reversed_list[index])
            card_tasks.append(task)
        
        processed_cards = await asyncio.gather(*card_tasks)
        
        # Composite all cards onto base image
        for card_img, position in processed_cards:
            base_img.alpha_composite(card_img, dest=position)
        
        return base_img

    async def _process_card(self, card_path: str, args: dict, is_reversed: bool) -> tuple:
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
    def __init__(self, model: str, url: str = DEFAULT_CONNECT_URL):
        self.is_busy = False # 是否繁忙
        self.tarot_data = None
        
        with open(TAROT_DATA_PATH, 'r', encoding='utf-8') as file:
            self.tarot_data = json.load(file)
        
        self.model = model
        self.client = ollama.AsyncClient(host=url)

    # 重新加载数据
    def reloadTarot(self):
        with open(TAROT_DATA_PATH, 'r', encoding='utf-8') as file:
            self.tarot_data = json.load(file)
    
    # 更新链接客服端
    def updateClient(self, model: str, url: str = DEFAULT_CONNECT_URL):
        self.model = model
        self.client = ollama.AsyncClient(host=url)

    # 属性文本处理
    def __handle_element_text(self, element, a_mod: bool = False, total_zodiacs_key: set = set()):
        result_text = ""
        
        element_name_cn = element["name_cn"]
                
        gender = element["genderCN"]
        color = ", ".join(element["colorsCN"])
        animals = element['animals']
        expression = element['expression']
        attribute = element['attribute']
        meaning = element['meaning']
                
        result_text += f"元素:{element_name_cn},能量属性:{gender},颜色:{color},生物:{animals},表达:{expression},属性:{attribute},含义:{meaning}"
        if a_mod:
            zodiac = element['zodiac']
            total_zodiacs_key.update(zodiac)
            zodiac_cn = ", ".join(element['zodiacCN'])
            result_text += f",元素对应星座:{zodiac_cn}"
        
        return result_text

    # 选择一套牌阵
    async def select_spreads(self, message: str):
        spreads_text = "可选的牌阵有:"
        
        spreads = self.tarot_data['spreads']
        
        for spread_id, info in spreads.items():
            spreads_text += f"\n{spread_id}: [\"{info['name_cn']}\", \"{info['description_cn']}\"]"
        
        messages = [
            {
                "role": "system",
                "content": TAROT_SPREADS + spreads_text,
            },
            {
                "role": "user",
                "content": message,
            },
        ]
        response = await self.client.chat(model=self.model, messages=messages)
        
        out_spread_key = TarotUtils.keep_english_digits(response['message']['content'].strip())
        
        if out_spread_key not in spreads:
            out_spread_key = DEFAULT_SPREAD_KEY
        
        return out_spread_key
        
    def __getTarotInfo(self, spread_key, card_keys, elem_keys, court_elem_corr_keys, ast_mod_keys, zodiacs_keys, is_reversed_list):
        datas = {
            "spread": self.tarot_data['spreads'][spread_key],
            "cards": {},
            "is_reversed_list": is_reversed_list,
            "astrologyModality": {},
            "courtElementalCorrespondence": {},
            "zodiacs": {},
            "elements": {}
        }
        
        for card_key in card_keys:
            datas["cards"][card_key] = self.tarot_data["cards"][card_key]
            
        for elem_key in elem_keys:
            datas["elements"][elem_key] = self.tarot_data["elements"][elem_key]
            
        for court_elem_corr_key in court_elem_corr_keys:
            datas["courtElementalCorrespondence"][court_elem_corr_key] = self.tarot_data["courtElementalCorrespondence"][court_elem_corr_key]
            
        for ast_mod_key in ast_mod_keys:
            datas["astrologyModality"][ast_mod_key] = self.tarot_data["astrologyModality"][ast_mod_key]
            
        for zodiacs_key in zodiacs_keys:
            datas["zodiacs"][zodiacs_key] = self.tarot_data["zodiacs"][zodiacs_key]
        
        return datas

    # user_message想要询问的信息, a_mod是否开启占星模式
    # is_busy为是否繁忙
    # card_select为卡牌选择模式,默认为78张塔罗牌全部选择,1为22张大阿尔卡那,2为56张小阿尔卡那
    async def divination(self, user_message: str, a_mod: bool = False, is_busy: bool = None, card_select: int = 0) -> TarotContent:
        if is_busy is not None:
            self.is_busy = is_busy
        result: TarotContent = TarotContent()
        result_texts = None
        complete_text = None
        failure_tips = None
        tarot_info = None
        tarot_text = None
        is_complete = False
        
        #######################
        # 基本塔罗牌
        # 阵形
        spreads = self.tarot_data['spreads']
        # 塔罗牌
        tarot_cards = self.tarot_data['cards']


        # 元素
        elements = self.tarot_data['elements']
        # 宫廷
        court_elemental_correspondence = self.tarot_data['courtElementalCorrespondence']

        #######################
        # 占星模式
        # 占星术情态
        astrology_modality = self.tarot_data['astrologyModality']
        # 十二星座
        zodiacs = self.tarot_data['zodiacs']
        # if True:
        is_reversed_list = []

        try:
            if self.is_busy:
                result.failure_text = random.choice(BUSY_TIPS)
                return result
                
            self.is_busy = True
            
            user_message = user_message
            user_message = TarotUtils.remove_emojis(user_message)
            
            # 啥啊这是
            if len(user_message) <= 0:
                result.failure_text = random.choice(NONE_TEXT_TIPS)
                return result
            elif len(user_message) > MAX_LENGTH:
                result.failure_text = TOO_LONG_TIP
                return result
            
            spread_key = await self.select_spreads(user_message)
            
            spread = spreads[spread_key]
            
            spread_name = spread["name_cn"]
            spread_description = spread["description_cn"]
            spread_positions = spread["positions"]
            card_count = len(spread_positions)
            
            tarot_cards_keys = list(tarot_cards.keys())
            if card_select == 1:
                tarot_cards_keys = tarot_cards_keys[:22]
            if card_select == 2:
                tarot_cards_keys = tarot_cards_keys[-56:]

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
            )
            
            response = await self.client.chat(model=self.model, messages=messages)
            
            out_texts = re.split(r'[\n。]', TarotUtils.replace_string(response["message"]["content"].strip()))
            
            result_texts = []
            for text in out_texts:
                if len(text.strip()) > 0:
                    hand_txt = text.strip().strip("。,，.").lstrip("？?!！").strip()
                    result_texts.append(hand_txt)
            
            datas = self.__getTarotInfo(spread_key, random_cards, total_elements, total_court_elemental_correspondence_keys, total_astrology_modality_keys, total_zodiacs_key, is_reversed_list)
            
            result.result_texts = result_texts
            result.tarot_text = show_text
            result.is_complete = True
            result.complete_text = random.choice(COMPLETE_TEXT_TIPS)
            result.tarot_info = datas
        except:
            result.failure_text = ERROR_TIP
            return result
        finally:
            self.is_busy = False
            
        return result
