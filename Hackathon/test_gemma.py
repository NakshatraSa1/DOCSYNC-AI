import asyncio
from google.antigravity import Agent, LocalOpenAIAgentConfig

async def main():
    config = LocalOpenAIAgentConfig(
        model="gemma4:e4b",
        base_url="http://localhost:11434/v1",
    ).lightweight()

    async with Agent(config) as agent:
        response = await agent.chat(
            "Reply exactly: PRIVPR GEMMA E4B SDK CONNECTED"
        )
        print(await response.text())

if __name__ == "__main__":
    asyncio.run(main())
