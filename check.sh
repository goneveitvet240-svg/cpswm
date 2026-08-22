#!/usr/bin/env bash
# CPSWM 本地检查脚本 —— 不做任何提交或推送，只跑检查并保存输出
cd "$(dirname "$0")" || exit 1
mkdir -p .checkout
echo "================ 1. 测试 ================"
uv run --extra dev pytest -n auto --cov=src --cov-report=term-missing \
  > .checkout/pytest.log 2>&1
PYTEST_RC=$?
tail -25 .checkout/pytest.log
echo "[pytest 退出码: ${PYTEST_RC}，完整日志: .checkout/pytest.log]"

echo
echo "================ 2. mypy (strict) ================"
uv run --extra dev mypy src > .checkout/mypy.log 2>&1
MYPY_RC=$?
tail -3 .checkout/mypy.log
echo "--- 错误按模块统计（Top 15）---"
grep -oE '^src/[^:]+' .checkout/mypy.log 2>/dev/null | sort | uniq -c | sort -rn | head -15
echo "--- 错误按类型统计（Top 10）---"
grep -oE '\[[a-z-]+\]$' .checkout/mypy.log 2>/dev/null | sort | uniq -c | sort -rn | head -10
echo "[mypy 退出码: ${MYPY_RC}，完整日志: .checkout/mypy.log]"

echo
echo "================ 3. ruff ================"
uv run --extra dev ruff check src tests --output-format=concise > .checkout/ruff.log 2>&1
echo "--- ruff 错误按规则统计 ---"
grep -oE ' [A-Z]+[0-9]+ ' .checkout/ruff.log | tr -d ' ' | sort | uniq -c | sort -rn
tail -3 .checkout/ruff.log
uv run --extra dev ruff format --check src tests 2>&1 | tail -3

echo
echo "================ 4. git 状态 ================"
echo "--- 本地领先远程的提交 ---"
git log origin/main..HEAD --oneline 2>/dev/null || echo "(无法比较，可能未 fetch)"
echo "--- 工作区 ---"
git status --short
echo "--- 已删除但仍在 git 历史里的文件 ---"
git log --diff-filter=D --name-only --pretty=format: HEAD 2>/dev/null | grep -E 'ra_research_proposal|research_note' | sort -u
