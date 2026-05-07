# Papers

本目录存放 DCPAM 项目的论文，每个目标期刊/会议对应一个独立文件夹。

## 目录结构

| 文件夹 | 目标期刊 | 模板 | 说明 |
|--------|---------|------|------|
| `IEEE/` | IEEE Transactions on Instrumentation and Measurement | IEEEtran | 主论文，完整的 DCPAM 模型与实验 |

## 编译方式

进入对应文件夹后执行：

```bash
xelatex dcpam.tex
xelatex dcpam.tex   # 再编译一次以解决交叉引用
```

## 开发约定

每次修改完 `.tex` 文件后，自动执行编译以确保改动不会引入编译错误。
