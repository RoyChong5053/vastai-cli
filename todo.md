# VastAI CLI 环境修复与隔离策略

## 问题分析
- 使用 `pip install --break-system-packages vastai` 破坏系统 Python 包完整性
- 损坏 `xdg` 模块导致 Hyprland 桌面无法启动（已修复）
- 系统其他 Python 包可能被污染，需全面检查

## 修复步骤

### 1. 系统 Python 包修复
```bash
# 检查系统包完整性
sudo pacman -Qkk python-pip python-pyxdg 2>/dev/null

# 重新安装系统 pip（如需要）
sudo pacman -S --needed python-pip

# 检查用户本地安装的包（可能冲突）
ls -la ~/.local/lib/python3.14/site-packages/ | grep -E "(vastai|xdg)"
```

### 2. 创建隔离环境（推荐）
```bash
# 使用 mamba 创建专用环境
mamba create -n vastai python=3.14 -y
mamba activate vastai

# 在环境中安装 vastai
pip install vastai

# 验证安装
python -c "import vastai; print(vastai.__version__)"
```

### 3. 项目适配
- 修改 `main.py` 和 `ssh_vastai.py` 的 shebang 指向环境 Python：
  ```python
  #!/home/roychong/miniforge3/envs/vastai/bin/python
  ```
- 或者创建包装脚本：
  ```bash
  #!/bin/bash
  source /home/roychong/miniforge3/etc/profile.d/conda.sh
  mamba activate vastai
  python /home/roychong/workspace/mycode/vastai_cli/main.py "$@"
  ```

### 4. 预防措施
- **永远不要**使用 `--break-system-packages`
- 使用虚拟环境或 conda 环境隔离项目依赖
- 考虑使用 `pipx` 安装 CLI 工具（如 vastai 支持）
- 定期检查 Python 路径：`python -c "import sys; print(sys.path)"`

## 可行策略选择

### 策略 A：使用现有 comfyui 环境
```bash
mamba activate comfyui
pip install vastai
```
优点：无需新建环境  
缺点：可能与其他依赖冲突

### 策略 B：新建专用环境（推荐）
```bash
mamba create -n vastai python=3.14 -y
mamba activate vastai
pip install vastai
```
优点：完全隔离，干净  
缺点：需要管理额外环境

### 策略 C：使用 pipx（如适用）
```bash
sudo pacman -S python-pipx
pipx install vastai
```
优点：自动隔离，全局可用  
缺点：需确认 vastai 是否支持 pipx 安装

## 已完成步骤
- [x] 卸载用户目录安装的 vastai 0.5.0
- [x] 创建专用 conda 环境 `vastai` (Python 3.14)
- [x] 在环境中安装 vastai 0.5.0 及其依赖
- [x] 创建包装脚本 `run.sh` 激活环境并运行项目
- [x] 检查系统包依赖冲突（python-dateutil 版本过低，但系统已阻止用户级升级）
- [x] 安装缺失依赖 `pyyaml`
- [x] 测试项目 `--help` 运行成功

## 下一步
1. 更新 README 说明使用 `run.sh` 而不是直接调用 `python main.py`
2. 测试完整功能（需要 API key）
3. 考虑将依赖列表导出为 `requirements.txt` 或 `environment.yml`
4. 添加 `environment.yml` 到项目，便于复现环境
5. 长期：将项目打包为可安装的 Python 包

## 长期改进
- 将项目打包为 Python 包，支持 `pip install -e .` 安装
- 添加 `environment.yml` 文件指定依赖
- 使用 `pyproject.toml` 管理依赖
- 考虑将 vastai 依赖移至可选，使用 subprocess 调用 CLI

---
*创建日期: 2026-03-25*
*基于修复文档: /home/roychong/workspace/note/cachyos_hyprland_fix_report.md*