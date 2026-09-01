#!/usr/bin/env bash
# CPSWM 本地检查脚本 —— 不做任何提交或推送，只跑检查并保存输出
cd "$(dirname "$0")" || exit 1
mkdir -p .checkout
UV_CACHE_DIR="$(pwd)/.checkout/uv-cache"
export UV_CACHE_DIR

if [[ -x .venv/bin/pytest && -x .venv/bin/mypy && -x .venv/bin/ruff ]]; then
  PYTEST_CMD=(.venv/bin/pytest)
  MYPY_CMD=(.venv/bin/mypy)
  RUFF_CMD=(.venv/bin/ruff)
else
  PYTEST_CMD=(uv run --extra dev pytest)
  MYPY_CMD=(uv run --extra dev mypy)
  RUFF_CMD=(uv run --extra dev ruff)
fi

echo "================ 1. 测试 ================"
"${PYTEST_CMD[@]}" -n auto --cov=src --cov-report=term-missing \
  > .checkout/pytest.log 2>&1
PYTEST_RC=$?
tail -25 .checkout/pytest.log
echo "[pytest 退出码: ${PYTEST_RC}，完整日志: .checkout/pytest.log]"

echo
echo "================ 2. mypy (strict) ================"
"${MYPY_CMD[@]}" src > .checkout/mypy.log 2>&1
MYPY_RC=$?
tail -3 .checkout/mypy.log
echo "--- 错误按模块统计（Top 15）---"
grep -oE '^src/[^:]+' .checkout/mypy.log 2>/dev/null | sort | uniq -c | sort -rn | head -15
echo "--- 错误按类型统计（Top 10）---"
grep -oE '\[[a-z-]+\]$' .checkout/mypy.log 2>/dev/null | sort | uniq -c | sort -rn | head -10
echo "[mypy 退出码: ${MYPY_RC}，完整日志: .checkout/mypy.log]"

echo
echo "================ 3. ruff ================"
"${RUFF_CMD[@]}" check src tests --output-format=concise > .checkout/ruff.log 2>&1
RUFF_RC=$?
echo "--- ruff 错误按规则统计 ---"
grep -oE ' [A-Z]+[0-9]+ ' .checkout/ruff.log | tr -d ' ' | sort | uniq -c | sort -rn
tail -3 .checkout/ruff.log
"${RUFF_CMD[@]}" format --check src tests > .checkout/ruff-format.log 2>&1
RUFF_FORMAT_RC=$?
tail -3 .checkout/ruff-format.log

echo
echo "================ 4. git 状态 ================"
echo "--- 本地领先远程的提交 ---"
git log origin/main..HEAD --oneline 2>/dev/null || echo "(无法比较，可能未 fetch)"
echo "--- 工作区 ---"
git status --short
echo "--- 已删除但仍在 git 历史里的文件 ---"
git log --diff-filter=D --name-only --pretty=format: HEAD 2>/dev/null | grep -E 'ra_research_proposal|research_note' | sort -u

if (( PYTEST_RC != 0 || MYPY_RC != 0 || RUFF_RC != 0 || RUFF_FORMAT_RC != 0 )); then
  exit 1
fi
