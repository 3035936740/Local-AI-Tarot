import argparse
import asyncio
import logging
import random

from tarot import Tarot, TarotContent, TarotDraw
from tarot_config import RESOURCES_DIR, TAROT_API_KEY, TAROT_MODEL, TAROT_PROVIDER, TAROT_URL

MIN_AWAIT_TIME, MAX_AWAIT_TIME = 1, 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="本地塔罗占卜")
    parser.add_argument("-q", "--question", default="我的重复梦境试图传达什么？")
    parser.add_argument("--url", default=TAROT_URL)
    parser.add_argument("--model", default=TAROT_MODEL)
    parser.add_argument(
        "--provider",
        default=TAROT_PROVIDER,
        choices=("ollama", "openai"),
        help="ollama 原生协议，或 openai 兼容接口",
    )
    parser.add_argument("--astrology", action="store_true", help="开启塔罗 + 占星")
    parser.add_argument(
        "--card-select",
        type=int,
        default=0,
        choices=(0, 1, 2),
        help="0=全牌组, 1=大阿尔卡那, 2=小阿尔卡那",
    )
    parser.add_argument("-o", "--output", default="output.png")
    parser.add_argument("--api-key", default=TAROT_API_KEY)
    return parser


async def example_div(args: argparse.Namespace) -> TarotContent:
    tarot = Tarot(args.model, args.url, api_key=args.api_key, provider=args.provider)
    result = await tarot.divination(args.question, args.astrology, card_select=args.card_select)

    if result.tarot_info:
        cards_list = list(result.tarot_info["cards"].values())
        drawer = TarotDraw(RESOURCES_DIR)
        image = await drawer.draw(
            cards_list,
            result.tarot_info["spread"],
            result.tarot_info["is_reversed_list"],
        )
        image.save(args.output)

    if result.is_complete:
        print(result.tarot_text)
        for out_text in result.result_texts:
            await asyncio.sleep(random.uniform(MIN_AWAIT_TIME, MAX_AWAIT_TIME))
            print(out_text.strip())
        print(result.complete_text)
    else:
        print(result.failure_text)
    return result


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args()
    await example_div(args)


if __name__ == "__main__":
    asyncio.run(main())
