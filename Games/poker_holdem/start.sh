#!/bin/bash
# 启动德州扑克游戏服务器

cd /data/workspace/work/data_stat/gr_pvm/poker

# 确保src目录在Python路径中
export PYTHONPATH="${PYTHONPATH}:/data/workspace/work/data_stat/gr_pvm/poker"

# 启动服务器
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
