import asyncio, random
from tarot import tarot

# 模拟塔罗师发消息
MIN_AWAIT_TIME, MAX_AWAIT_TIME = 1, 3

async def main():
    question = "我的重复梦境试图传达什么？" # 想要询问的问题
    is_astrology = False # 是否开启塔罗牌 + 占星，False为经典塔罗牌模式
    result = await tarot(question, is_astrology)
    
    data = result.tarot_info
    
    if result.is_complete:
        print(result.tarot_text)
        for out_text in result.result_texts:
            random_float = random.uniform(MIN_AWAIT_TIME, MAX_AWAIT_TIME)
            await asyncio.sleep(random_float)
            print(out_text.strip())
        
        print(result.complete_text)
    else:
        print(result.failure_text)

if __name__ == "__main__":
    asyncio.run(main())