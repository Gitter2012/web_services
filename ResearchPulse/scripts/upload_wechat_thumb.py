#!/usr/bin/env python3
# =============================================================================
# 脚本: scripts/upload_wechat_thumb.py
# 功能: 上传图片到微信公众号永久素材，获取 media_id
# 用法: python scripts/upload_wechat_thumb.py [图片路径] [--type image|thumb]
#       默认上传 data/imgs/default_cat.png，类型为 image
# 说明:
#   - image 类型: 支持大图（最大 10MB），适合封面图和正文图片
#   - thumb 类型: 缩略图（最大 64KB），适合小缩略图
# =============================================================================

"""Upload an image as permanent material to WeChat MP and print the media_id."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 将项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from settings import settings
from common.wechat_mp.client import WeChatMPClient, WeChatAPIError


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="上传图片到微信公众号永久素材并获取 media_id"
    )
    parser.add_argument(
        "image_path",
        nargs="?",
        default=str(PROJECT_ROOT / "data" / "imgs" / "default_cat.png"),
        help="图片文件路径（默认: data/imgs/default_cat.png）",
    )
    parser.add_argument(
        "--type",
        dest="media_type",
        choices=["image", "thumb"],
        default="image",
        help="素材类型: image（大图，最大10MB）或 thumb（缩略图，最大64KB），默认 image",
    )
    args = parser.parse_args()

    image_path = Path(args.image_path)

    # 校验
    if not image_path.exists():
        print(f"[ERROR] 图片文件不存在: {image_path}")
        sys.exit(1)

    if not settings.wechat_mp_appid or not settings.wechat_mp_secret:
        print("[ERROR] 请先在 .env 中配置 WECHAT_MP_APPID 和 WECHAT_MP_SECRET")
        sys.exit(1)

    file_size_kb = image_path.stat().st_size / 1024
    print(f"图片路径:   {image_path}")
    print(f"文件大小:   {file_size_kb:.1f} KB")
    print(f"素材类型:   {args.media_type}")
    print(f"AppID:     {settings.wechat_mp_appid[:8]}...")

    # thumb 类型限制 64KB
    if args.media_type == "thumb" and file_size_kb > 64:
        print(f"\n[WARNING] thumb 类型限制 64KB，当前文件 {file_size_kb:.1f} KB，可能上传失败")
        print("建议使用 --type image（默认）上传大图")

    print()

    # 读取图片
    image_data = image_path.read_bytes()
    filename = image_path.name

    # 上传
    client = WeChatMPClient(
        appid=settings.wechat_mp_appid,
        secret=settings.wechat_mp_secret,
    )

    try:
        print("正在获取 access_token...")
        print("正在上传永久素材...")

        media_id = await client.upload_permanent_material(
            image_data=image_data,
            filename=filename,
            media_type=args.media_type,
        )

        print()
        print("=" * 60)
        print("上传成功!")
        print(f"media_id = {media_id}")
        print("=" * 60)
        print()
        print("请将以下值填入 .env 文件:")
        print(f"WECHAT_MP_DEFAULT_THUMB={media_id}")

    except WeChatAPIError as e:
        print(f"\n[ERROR] 微信 API 错误: errcode={e.errcode}, errmsg={e.errmsg}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 上传失败: {e}")
        sys.exit(1)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
