工具不支持 $\theta$ 符号，我直接手算。

$$E[X_{(n)}] = \int_0^\theta x\cdot\frac{nx^{n-1}}{\theta^n}\,dx = \frac{n}{\theta^n}\cdot\frac{\theta^{n+1}}{n+1} = \frac{n}{n+1}\theta$$

$$E[X_{(n)}^2] = \int_0^\theta x^2\cdot\frac{nx^{n-1}}{\theta^n}\,dx = \frac{n}{\theta^n}\cdot\frac{\theta^{n+2}}{n+2} = \frac{n}{n+2}\theta^2$$

---

## (1) 无偏估计

$$E[T_c] = cE[X_{(n)}] = c\cdot\frac{n}{n+1}\theta$$

令 $E[T_c]=\theta$，得

$$\boxed{c=\frac{n+1}{n}}$$

---

## (2) 最小均方误差

$$h(c)=E[(T_c-\theta)^2]=c^2E[X_{(n)}^2]-2c\theta E[X_{(n)}]+\theta^2$$

代入矩：

$$h(c)=\theta^2\left[\frac{n}{n+2}c^2-\frac{2n}{n+1}c+1\right]$$

对 $c$ 求导并令其为零：

$$h'(c)=\theta^2\left[\frac{2n}{n+2}c-\frac{2n}{n+1}\right]=0$$

解得

$$\boxed{c^*=\frac{n+2}{n+1}}$$

代入求最小值：

$$h(c^*)=\theta^2\left[\frac{n}{n+2}\cdot\frac{(n+2)^2}{(n+1)^2}-\frac{2n}{n+1}\cdot\frac{n+2}{n+1}+1\right]$$

$$=\theta^2\left[\frac{n(n+2)}{(n+1)^2}-\frac{2n(n+2)}{(n+1)^2}+1\right]=\theta^2\left[1-\frac{n(n+2)}{(n+1)^2}\right]$$

$$=\theta^2\cdot\frac{(n+1)^2-n(n+2)}{(n+1)^2}=\theta^2\cdot\frac{1}{(n+1)^2}$$

$$\boxed{h_{\min}=\frac{\theta^2}{(n+1)^2}}$$

---

**对比小结：** 无偏估计取 $c=\frac{n+1}{n}$，而最小均方误差估计取 $c=\frac{n+2}{n+1}$（后者偏小，是有偏估计）。均方误差的降低来自偏差与方差的权衡。

> 回答验收未通过：未找到该分项的核心对象, 未找到该分项的核心对象。这些结论仍需核对。