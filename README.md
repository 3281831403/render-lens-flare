# render-lens-flare

## 题面

给镜头加光晕后，鬼影全挤在光源一侧、被墙挡住还照样亮：鬼影不沿中心对称，全在光源侧；越界不剔除，绘制到画布外；遮挡用亮度阈值，暗背景误判为遮挡；色差偏移所有通道同向，等于没分；光圈遮罩用圆形，多边形消失；光晕方向与光源同向，应该反向；衰减用线性，边缘生硬；强度越界不钳制，过曝；批量共用鬼影列表，光源之间串；count<=0 不校验，除零。flare/lens.py 是核心，tests/test_lens.py 15个红。要修的是：让鬼影沿画面中心对称分布并剔除越界项、按深度图而不是亮度做遮挡、让红色和蓝色色差反向偏移、改用多边形光圈遮罩、把光晕放到光源的反向、使用平滑衰减、校验并拒绝越界强度、隔离每个光源的鬼影列表、校验 count 并消除除零。

## 运行方式

在仓库根目录执行：

```powershell
python -m pytest tests -q
```

初始状态应恰好得到 `15 failed`，并且没有 collection error、import error 或 syntax error。修复 `flare/lens.py` 后，这 15 条测试应全部通过。

## 字段表

| 字段 | 取值 |
| --- | --- |
| 所属领域 | 游戏、图形与多媒体 |
| 子方向 | 图形渲染 |
| 任务类型 | Bugfix |
| 语言/框架 | Python 3, pytest |
| 环境可复现等级 | 无外部依赖 |

## 约束

- 只使用 Python 标准库（`math`）与 pytest；离线运行，不使用随机数，采样结果确定。
- 屏幕坐标使用归一化 UV，范围 `[0, 1]`；光源形如 `{"uv": (u, v), "intensity": 0..1}`。
- 强度、遮罩与颜色通道均为 `0..1`；浮点比较容差为 `1e-6`。
- 八个公开函数的输入输出契约见 `flare/lens.py` 的 docstring，非法输入通过 `FlareError` 报告。
- `tests/test_lens.py` 不可修改；它是验收契约，不是待改代码。

## 文件

```text
render-lens-flare/
  README.md
  conftest.py
  .gitignore
  flare/
    __init__.py
    lens.py
  tests/
    test_lens.py
```
