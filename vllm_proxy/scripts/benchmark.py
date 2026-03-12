#!/usr/bin/env python3
"""性能测试脚本 - 测试推理速度和并发性能"""

import argparse
import asyncio
import time
import sys
import json

sys.path.insert(0, '/data/workspace/apps/vllm_proxy')
from client import VLLMProxyAsyncClient

BASE_URL = "http://localhost:11436"

parser = argparse.ArgumentParser(description="vLLM Proxy 性能测试")
parser.add_argument("--model", default="qwen3.5-9b-awq-4bit", help="测试的模型名称")
parser.add_argument("--base-url", default=BASE_URL, help="代理服务地址")
args = parser.parse_args()

MODEL = args.model
BASE_URL = args.base_url


async def test_single_request(client, max_tokens=256):
    """测试单个请求的推理速度"""
    start = time.time()
    response = await client.chat_completion(
        model=MODEL,
        messages=[{"role": "user", "content": "请用100字介绍一下人工智能"}],
        max_tokens=max_tokens,
        temperature=0.7
    )
    elapsed = time.time() - start

    # 计算实际生成的 token 数
    content = response['choices'][0]['message']['content']
    usage = response.get('usage', {})
    output_tokens = usage.get('completion_tokens', len(content) // 2)

    return {
        'elapsed': elapsed,
        'output_tokens': output_tokens,
        'tokens_per_second': output_tokens / elapsed if elapsed > 0 else 0,
        'content_length': len(content)
    }


async def test_concurrent_requests(client, num_requests=5, max_tokens=128):
    """测试并发请求性能"""
    async def single_request(idx):
        start = time.time()
        response = await client.chat_completion(
            model=MODEL,
            messages=[{"role": "user", "content": f"用一句话回答：{idx}+1等于多少？"}],
            max_tokens=max_tokens,
            temperature=0.1
        )
        elapsed = time.time() - start
        usage = response.get('usage', {})
        output_tokens = usage.get('completion_tokens', 10)
        return elapsed, output_tokens

    start = time.time()
    results = await asyncio.gather(*[single_request(i) for i in range(num_requests)])
    total_time = time.time() - start

    total_tokens = sum(r[1] for r in results)
    avg_latency = sum(r[0] for r in results) / len(results)

    return {
        'total_time': total_time,
        'total_tokens': total_tokens,
        'throughput_tokens_per_sec': total_tokens / total_time,
        'throughput_req_per_sec': num_requests / total_time,
        'avg_latency': avg_latency,
        'min_latency': min(r[0] for r in results),
        'max_latency': max(r[0] for r in results),
    }


async def wait_for_model_ready(client, timeout=300):
    """等待模型加载完成"""
    print(f"加载模型 {MODEL}...")
    start = time.time()

    # 触发模型加载
    try:
        await client.load_model(MODEL)
    except Exception as e:
        print(f"加载模型时出错: {e}")

    # 等待模型就绪
    while time.time() - start < timeout:
        health = await client.health_check()
        model_status = health.get('model_status', {})
        if MODEL in model_status:
            status = model_status[MODEL].get('status', 'unknown')
            if status == 'running':
                print(f"模型已就绪，耗时 {time.time() - start:.1f}s")
                return True
            elif status == 'error':
                print(f"模型加载失败")
                return False
        await asyncio.sleep(2)

    print("等待模型超时")
    return False


async def main():
    print("=" * 60)
    print(f"性能测试 - {MODEL}")
    print("=" * 60)

    client = VLLMProxyAsyncClient(base_url=BASE_URL)

    try:
        # 检查服务状态
        health = await client.health_check()
        print(f"GPU: {health['gpu']['name']}")
        print(f"显存: {health['gpu']['memory']['used_mb']}/{health['gpu']['memory']['total_mb']} MiB")
        print()

        # 等待模型加载
        if not await wait_for_model_ready(client):
            return

        # 等待模型稳定
        print("\n等待模型稳定...")
        await asyncio.sleep(5)

        # 测试 1: 单请求推理速度
        print("\n" + "-" * 40)
        print("测试 1: 单请求推理速度 (3次平均)")
        print("-" * 40)

        single_results = []
        for i in range(3):
            result = await test_single_request(client, max_tokens=256)
            single_results.append(result)
            print(f"  第 {i+1} 次: {result['tokens_per_second']:.1f} tokens/s, "
                  f"{result['output_tokens']} tokens in {result['elapsed']:.2f}s")
            await asyncio.sleep(1)

        avg_tps = sum(r['tokens_per_second'] for r in single_results) / len(single_results)
        avg_latency = sum(r['elapsed'] for r in single_results) / len(single_results)
        print(f"\n  平均: {avg_tps:.1f} tokens/s, 延迟 {avg_latency:.2f}s")

        # 测试 2: 并发请求
        print("\n" + "-" * 40)
        print("测试 2: 并发请求 (5/10/20 并发)")
        print("-" * 40)

        for concurrency in [5, 10, 20]:
            result = await test_concurrent_requests(client, num_requests=concurrency)
            print(f"\n  并发 {concurrency}:")
            print(f"    总耗时: {result['total_time']:.2f}s")
            print(f"    吞吐量: {result['throughput_tokens_per_sec']:.1f} tokens/s")
            print(f"    吞吐量: {result['throughput_req_per_sec']:.2f} req/s")
            print(f"    平均延迟: {result['avg_latency']:.2f}s")
            await asyncio.sleep(2)

        # 最终显存状态
        health = await client.health_check()
        print("\n" + "-" * 40)
        print("最终状态")
        print("-" * 40)
        print(f"显存使用: {health['gpu']['memory']['used_mb']}/{health['gpu']['memory']['total_mb']} MiB")

        # 输出结果摘要
        print("\n" + "=" * 60)
        print("测试结果摘要")
        print("=" * 60)
        print(f"单请求平均速度: {avg_tps:.1f} tokens/s")
        print(f"单请求平均延迟: {avg_latency:.2f}s")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
