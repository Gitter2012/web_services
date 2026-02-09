#!/usr/bin/env python3
"""
快速游戏测试
"""
import asyncio
import websockets
import json

async def test():
    uri = "ws://127.0.0.1:8000/ws/TestUser"
    try:
        ws = await websockets.connect(uri)
        print("✓ 连接成功")

        msg = await asyncio.wait_for(ws.recv(), timeout=3)
        data = json.loads(msg)
        print(f"✓ 收到消息: {data.get('type')}")

        await ws.close()
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test())
    print("测试结果:", "成功" if result else "失败")
