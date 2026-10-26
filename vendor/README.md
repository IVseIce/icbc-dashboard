# vendor/ —— 随包走的第三方依赖

内网机**没有外网、没有 pip**，所以依赖必须跟着包走。这里放的是**纯 Python** 包
（wheel 标签 `py2.py3-none-any`），与 CPU 架构无关，arm64 / x86_64 都能用。

## 当前版本

| 包 | 版本 | 来源 |
|---|---|---|
| openpyxl | 3.1.5 | `openpyxl-3.1.5-py2.py3-none-any.whl` |
| xlrd | 2.0.1 | `xlrd-2.0.1-py2.py3-none-any.whl` |
| PyYAML | 6.0.2 | wheel 的**纯 Python 部分**（删掉了 `yaml/_yaml*.so`、`_yaml/`、`PyYAML.libs/`） |
| et_xmlfile | 2.0.0 | openpyxl 依赖 |

PyYAML 的 C 加速模块是 x86_64 的 `.so`，在 arm64 上会直接崩，所以**必须删掉**；
删掉后 `yaml` 自动退回纯 Python 实现（`yaml.__with_libyaml__ == False`），本项目只用 `safe_load`，够用。

## 怎么重建

```bash
rm -rf vendor/pylib && mkdir -p vendor/pylib
pip install --target vendor/pylib --no-compile openpyxl==3.1.5 xlrd==2.0.1 PyYAML==6.0.2
rm -rf vendor/pylib/_yaml vendor/pylib/PyYAML.libs vendor/pylib/bin
find vendor/pylib/yaml -name '_yaml*' -delete
du -sh vendor/pylib          # 约 2.2 MB
PYTHONPATH=vendor/pylib python3 -c "import openpyxl, xlrd, yaml; print(yaml.__with_libyaml__)"
```

改版本时同步 `requirements.txt`，并重跑 `scripts/selftest.py`。
