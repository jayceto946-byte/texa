# 用斯托克斯公式计算曲线积分

## 1. 分析曲线与方向

**球面** $x^2+y^2+z^2=2x$ 即 $(x-1)^2+y^2+z^2=2$，球心 $(1,0,0)$，半径 $\sqrt{2}$。

**平面** $2x-z-1=0$ 即 $z=2x-1$。

将 $z=2x-1$ 代入球面方程，得交线 $L$ 在 $xy$ 平面的投影：
$$x^2+y^2+(2x-1)^2=2x \implies 5x^2-6x+1+y^2=0$$
配方：
$$5\left(x-\frac{3}{5}\right)^2+y^2=\frac{4}{5} \implies \frac{(x-3/5)^2}{(2/5)^2}+\frac{y^2}{(2/\sqrt{5})^2}=1$$

**投影区域 $D_{xy}$** 是该椭圆围成的区域，半轴 $a=\dfrac{2}{5}$，$b=\dfrac{2}{\sqrt{5}}$。

**方向判定**：从 $z$ 轴正向往下看为逆时针，由右手定则，曲面法向量 $\mathbf{n}$ 的 $z$ 分量应为正。平面 $2x-z=1$ 的法向量取 $\mathbf{n}=\dfrac{(-2,0,1)}{\sqrt{5}}$（$z$ 分量为正）。

## 2. 选取曲面

取 $\Sigma$ 为平面 $z=2x-1$ 上被 $L$ 围成的椭圆盘，方向朝上（法向量 $\mathbf{n}$ 如上）。

## 3. 计算旋度

记 $P=6xyz-yz^2$，$Q=2x^2z$，$R=xyz$。

$$\nabla\times\mathbf{F}=\left(\frac{\partial R}{\partial y}-\frac{\partial Q}{\partial z},\;\frac{\partial P}{\partial z}-\frac{\partial R}{\partial x},\;\frac{\partial Q}{\partial x}-\frac{\partial P}{\partial y}\right)$$

逐项计算：
- $\dfrac{\partial R}{\partial y}-\dfrac{\partial Q}{\partial z}=xz-2x^2$
- $\dfrac{\partial P}{\partial z}-\dfrac{\partial R}{\partial x}=(6xy-2yz)-yz=6xy-3yz$
- $\dfrac{\partial Q}{\partial x}-\dfrac{\partial P}{\partial y}=4xz-(6xz-z^2)=-2xz+z^2$

## 4. 转化为二重积分

面积元素关系：$dS=\sqrt{1+z_x^2+z_y^2}\,dxdy=\sqrt{1+4+0}\,dxdy=\sqrt{5}\,dxdy$

$$\mathbf{n}\,dS=\frac{(-2,0,1)}{\sqrt{5}}\cdot\sqrt{5}\,dxdy=(-2,0,1)\,dxdy$$

被积函数：
$$(\nabla\times\mathbf{F})\cdot(-2,0,1)=-2(xz-2x^2)+0+(-2xz+z^2)=4x^2-4xz+z^2=(2x-z)^2$$

在曲面 $\Sigma$ 上 $z=2x-1$，故 $2x-z=1$，被积函数恒为 **1**。

## 5. 计算结果

$$\oint_L \mathbf{F}\cdot d\mathbf{r}=\iint_{D_{xy}}1\,dxdy=\text{Area}(D_{xy})=\pi\cdot\frac{2}{5}\cdot\frac{2}{\sqrt{5}}=\boxed{\dfrac{4\sqrt{5}\,\pi}{25}}$$

> 回答验收未通过：未找到该分项的核心对象, 未找到该分项的核心对象, 未找到该分项的核心对象。这些结论仍需核对。