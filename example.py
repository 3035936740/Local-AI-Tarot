import asyncio, random
from tarot import Tarot, TarotContent, TarotDraw

# 运行的URL
URL = "http://localhost:11434"
# 选择的模型
MODEL = "llama3.1:latest"

# 模拟塔罗师发消息
MIN_AWAIT_TIME, MAX_AWAIT_TIME = 1, 3

async def example_div():
    tarot = Tarot(URL, MODEL)
    question = "我的重复梦境试图传达什么？" # 想要询问的问题
    is_astrology = False # 是否开启塔罗牌 + 占星，False为经典塔罗牌模式
    result: TarotContent = await tarot.divination(question, is_astrology, card_select=0)
    
    data = result.tarot_info
    print(data)
    
    if result.is_complete:
        print(result.tarot_text)
        for out_text in result.result_texts:
            random_float = random.uniform(MIN_AWAIT_TIME, MAX_AWAIT_TIME)
            await asyncio.sleep(random_float)
            print(out_text.strip())
        
        print(result.complete_text)
    else:
        print(result.failure_text)

async def example_draw():
    from tarot_config import TAROT_DATA_PATH
    import json
    with open(TAROT_DATA_PATH, 'r', encoding='utf-8') as file:
        tarot_data = json.load(file)
    
    spread_key = "dreamMatrix"
    # 阵法
    spreads = tarot_data['spreads']
    # 塔罗牌
    tarot_cards = tarot_data['cards']

    spread = spreads[spread_key]
    tarot_cards_keys = list(tarot_cards.keys())
    spread_positions = spread["positions"]
    card_count = len(spread_positions)
    random_cards = random.sample(tarot_cards_keys, card_count)

    cards = [tarot_cards[random_card] for random_card in random_cards]
    is_reversed_list = random.choices([True, False], k=card_count)

    tarot_draw = TarotDraw("resources")
    result = await tarot_draw.draw(cards, spread, is_reversed_list)
    result.save("output.png")

async def main():
    await example_draw() # 绘图
    # await example_div() # 占比

if __name__ == "__main__":
    asyncio.run(main())
