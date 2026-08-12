import sys
import asyncio
import traceback
from app.copilot import RedisCopilot

async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m app.cli \"your question here\"")
        sys.exit(1)
        
    question = sys.argv[1]
    copilot = RedisCopilot()
    
    try:
        answer = await copilot.ask(question)
        print(answer)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc()
        raise SystemExit(1)

if __name__ == "__main__":
    asyncio.run(main())
