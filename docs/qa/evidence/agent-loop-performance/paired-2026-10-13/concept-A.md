## 可导与连续的关系

**可导必连续，连续不一定可导。**

### 可导 ⇒ 连续

若 $f(x)$ 在 $x_0$ 处可导，则 $f(x)$ 在 $x_0$ 处连续。

**证明思路：** 由可导定义，$\lim_{\Delta x \to 0} \frac{f(x_0 + \Delta x) - f(x_0)}{\Delta x} = f'(x_0)$ 存在。

则 $\lim_{\Delta x \to 0} [f(x_0 + \Delta x) - f(x_0)] = \lim_{\Delta x \to 0} \frac{f(x_0 + \Delta x) - f(x_0)}{\Delta x} \cdot \Delta x = f'(x_0) \cdot 0 = 0$

即 $\lim_{\Delta x \to 0} f(x_0 + \Delta x) = f(x_0)$，这正是连续的定义。

**直观理解：** 可导要求函数在该点附近"光滑"，而光滑必然意味着没有断裂，所以连续。

### 连续 ⇏ 可导

连续只要求函数值没有跳跃，但允许图像出现"尖角"或"折点"，这些位置就不可导。

## 反例：$f(x) = |x|$ 在 $x = 0$ 处

**连续性验证：**
$$\lim_{x \to 0} |x| = 0 = f(0)$$
故 $f(x)$ 在 $x = 0$ 处连续。

**不可导性验证：**

计算左右导数：

**左导数：**
$$f'_-(0) = \lim_{\Delta x \to 0^-} \frac{f(0 + \Delta x) - f(0)}{\Delta x} = \lim_{\Delta x \to 0^-} \frac{|\Delta x|}{\Delta x} = \lim_{\Delta x \to 0^-} \frac{-\Delta x}{\Delta x} = -1$$

**右导数：**
$$f'_+(0) = \lim_{\Delta x \to 0^+} \frac{f(0 + \Delta x) - f(0)}{\Delta x} = \lim_{\Delta x \to 0^+} \frac{|\Delta x|}{\Delta x} = \lim_{\Delta x \to 0^+} \frac{\Delta x}{\Delta x} = 1$$

由于 $f'_-(0) = -1 \neq 1 = f'_+(0)$，左右导数不相等，故 $f(x) = |x|$ 在 $x = 0$ 处不可导。

**几何直观：** $f(x) = |x|$ 的图像在 $x = 0$ 处形成一个"尖角"，从左侧看斜率为 $-1$，从右侧看斜率为 $+1$，在该点没有唯一的切线斜率，因此不可导。

> 回答核对：部分公式或数值尚无确定性核验依据，请核对后使用。