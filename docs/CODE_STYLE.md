# DCPAM 代码规范

## 项目结构

```
dcpam/
├── dcpam-cv/          # 核心代码模块（传统CV模型）
├── dcpam-mlp/         # 核心代码模块（MLP模型）
├── dcpam-cnn/         # 核心代码模块（CNN模型）
├── scripts/           # 可直接执行的脚本文件
├── docs/              # 项目文档
└── tests/             # 测试文件
```

## 核心原则

### 1. 项目组织原则

- **核心代码模块**：放在 `dcpam-cv/`、`dcpam-mlp/`、`dcpam-cnn/` 等目录下
  - 包含可复用的函数、类和算法实现
  - 需要通过 `import` 导入使用
  - 不应直接执行

- **可执行脚本**：放在 `scripts/` 目录下
  - 直接运行的 Python 脚本
  - **不推荐使用 CLI 框架**（如 argparse、click 等）
  - 使用简单的配置文件或在脚本顶部定义常量
  - 命名清晰表明用途，如 `train_model.py`、`process_images.py`

### 2. 脚本编写规范

#### ✅ 推荐的脚本写法

```python
#!/usr/bin/env python3
"""
脚本功能简要说明
"""
from pathlib import Path
from dcpam_cv.core import process_image

# 配置参数（在脚本顶部集中定义）
INPUT_DIR = Path("data/raw")
OUTPUT_DIR = Path("data/processed")
THRESHOLD = 0.5
ENABLE_DEBUG = True


def main():
    """主执行函数"""
    print(f"Processing images from {INPUT_DIR}")

    # 执行逻辑
    for img_path in INPUT_DIR.glob("*.jpg"):
        result = process_image(img_path, threshold=THRESHOLD)
        # ...

    print("Done!")


if __name__ == "__main__":
    main()
```

#### ❌ 避免的写法

```python
# 不推荐：使用复杂的 CLI 框架
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    # ... 大量参数定义
    args = parser.parse_args()
```

脚本应该简单直接，需要修改参数时直接编辑脚本更清晰高效。

### 3. Python 代码风格

#### 基本规范

- **缩进**：使用 4 个空格
- **行宽**：建议不超过 100 字符
- **编码**：UTF-8
- **Python 版本**：>=3.12

#### 命名约定

```python
# 模块/包：小写+下划线
dcpam_cv/
    image_processor.py

# 类：大驼峰命名
class ImageProcessor:
    pass

class DualCameraModel:
    pass

# 函数/方法：小写+下划线
def process_image(img_path):
    pass

def calculate_point_to_axis():
    pass

# 常量：全大写+下划线
MAX_ITERATIONS = 100
DEFAULT_THRESHOLD = 0.5

# 变量：小写+下划线
image_path = Path("data/image.jpg")
camera_matrix = np.array([...])
```

#### 导入顺序

```python
# 1. 标准库
import os
import sys
from pathlib import Path

# 2. 第三方库
import numpy as np
import cv2
from scipy import optimize

# 3. 本地模块
from dcpam_cv.core import process_image
from dcpam_cv.utils import load_config
```

