"""检查相机运行环境：numpy 版本 + gxipy 导入 + 相机检测。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

print(f"[env] python     : {sys.version.split()[0]}")
print(f"[env] numpy      : {np.__version__}")

if int(np.__version__.split(".")[0]) >= 2:
    print("[FAIL] numpy >= 2, gxipy 会因 numpy.compat 被移除而失败。请 uv pip install numpy==1.26.4")
    sys.exit(1)

sdk_root = Path("D:/Camera_Galaxy/GalaxySDK")
py_path = sdk_root / "Development" / "Samples" / "Python"
dll_path = sdk_root / "APIDll" / "Win64"
gentl_path = sdk_root / "GenICam" / "bin" / "Win64_x64"

print(f"[env] SDK python : {py_path} (exists={py_path.exists()})")
print(f"[env] SDK dll    : {dll_path} (exists={dll_path.exists()})")
print(f"[env] SDK gentl  : {gentl_path} (exists={gentl_path.exists()})")

sys.path.insert(0, str(py_path))
os.environ["PATH"] = f"{dll_path}{os.pathsep}{gentl_path}{os.pathsep}" + os.environ.get("PATH", "")

try:
    import gxipy as gx
except Exception as exc:
    print(f"[FAIL] gxipy 导入失败: {exc}")
    sys.exit(2)

print("[ok]  gxipy 导入成功")

try:
    dm = gx.DeviceManager()
    dev_num, dev_info_list = dm.update_device_list()
    print(f"[ok]  检测到相机数量: {dev_num}")
    for i, info in enumerate(dev_info_list, start=1):
        sn = info.get("sn", "?")
        model = info.get("model_name", "?")
        vendor = info.get("vendor_name", "?")
        ip = info.get("ip", "?")
        print(f"  cam{i}: model={model}  sn={sn}  vendor={vendor}  ip={ip}")
    if dev_num < 2:
        print("[warn] 不足 2 台相机，DualCamera 需要 2 台。")
except Exception as exc:
    print(f"[FAIL] 相机检测失败: {exc}")
    sys.exit(3)
