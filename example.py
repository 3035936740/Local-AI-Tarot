import asyncio, random
from tarot import Tarot, TarotContent, TarotDraw

# 运行的URL
URL = "192.168.0.106:11434"
# 选择的模型
MODEL = "llama3.2-vision:latest" # "llama3.1:latest" 

# 模拟塔罗师发消息
MIN_AWAIT_TIME, MAX_AWAIT_TIME = 1, 3

async def example_div():
    tarot = Tarot(MODEL, URL)
    question = "我的重复梦境试图传达什么？" # 想要询问的问题
    is_astrology = False # 是否开启塔罗牌 + 占星，False为经典塔罗牌模式
    result: TarotContent = await tarot.divination(question, is_astrology, card_select=0)
    
    data = result.tarot_info
    print(data)
    cards_list = [value for __,value in data["cards"].items()]
    tarot_draw = TarotDraw("resources")
    result_draw = await tarot_draw.draw(cards_list, data["spread"], data["is_reversed_list"])
    result_draw.save("output.png")
    
    if result.is_complete:
        print(result.tarot_text)
        for out_text in result.result_texts:
            random_float = random.uniform(MIN_AWAIT_TIME, MAX_AWAIT_TIME)
            await asyncio.sleep(random_float)
            print(out_text.strip())
        
        print(result.complete_text)
    else:
        print(result.failure_text)

async def main():
    await example_div() # 占卜

if __name__ == "__main__":
    asyncio.run(main())
