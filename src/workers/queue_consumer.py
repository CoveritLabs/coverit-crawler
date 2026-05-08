import asyncio
from src.workers.consumers.stream_to_arq import main as _main


async def main() -> int:
    return await _main()

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
