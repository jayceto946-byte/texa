**1. 写出矩阵 $A$**

由递推关系 $x_n=-2x_{n-1}+2z_{n-1}$，$y_n=-2y_{n-1}-2z_{n-1}$，$z_n=-6x_{n-1}-3y_{n-1}+3z_{n-1}$，可将其写为矩阵形式 $\alpha_n = A\alpha_{n-1}$，其中：
$$A = \begin{pmatrix} -2 & 0 & 2 \\ 0 & -2 & -2 \\ -6 & -3 & 3 \end{pmatrix}$$

**2. 求 $A^n$ 及推导过程**

首先求 $A$ 的特征值与特征向量。特征多项式为：
$$|\lambda I - A| = \begin{vmatrix} \lambda + 2 & 0 & -2 \\ 0 & \lambda + 2 & 2 \\ 6 & 3 & \lambda - 3 \end{vmatrix} = \lambda(\lambda + 2)(\lambda - 1)$$
解得特征值 $\lambda_1 = 0,\ \lambda_2 = -2,\ \lambda_3 = 1$。

分别求解对应的特征向量：
- 当 $\lambda_1 = 0$ 时，解 $-Ax=0$，得特征向量 $v_1 = (1, -1, 1)^T$；
- 当 $\lambda_2 = -2$ 时，解 $(-2I - A)x=0$，得特征向量 $v_2 = (1, -2, 0)^T$；
- 当 $\lambda_3 = 1$ 时，解 $(I - A)x=0$，得特征向量 $v_3 = (2, -2, 3)^T$。

令可逆矩阵 $P = (v_1, v_2, v_3) = \begin{pmatrix} 1 & 1 & 2 \\ -1 & -2 & -2 \\ 1 & 0 & 3 \end{pmatrix}$，则 $A = P \Lambda P^{-1}$，其中 $\Lambda = \text{diag}(0, -2, 1)$。
计算 $P$ 的逆矩阵：
$$P^{-1} = \begin{pmatrix} 6 & 3 & -2 \\ -1 & -1 & 0 \\ -2 & -1 & 1 \end{pmatrix}$$

由 $A^n = P \Lambda^n P^{-1}$，其中 $\Lambda^n = \text{diag}(0^n, (-2)^n, 1^n)$。
**关于 $n=0$ 的情况说明**：在矩阵幂运算中，为保证 $A^0 = I$（单位矩阵），必须规定 $0^0 = 1$。而当 $n \ge 1$ 时，$0^n = 0$。因此 $A^n$ 需分段表示：

- **当 $n \ge 1$ 时**，$0^n = 0$：
$$A^n = \begin{pmatrix} 1 & 1 & 2 \\ -1 & -2 & -2 \\ 1 & 0 & 3 \end{pmatrix} \begin{pmatrix} 0 & 0 & 0 \\ 0 & (-2)^n & 0 \\ 0 & 0 & 1 \end{pmatrix} \begin{pmatrix} 6 & 3 & -2 \\ -1 & -1 & 0 \\ -2 & -1 & 1 \end{pmatrix} = \begin{pmatrix} -(-2)^n - 4 & -(-2)^n - 2 & 2 \\ 2(-2)^n + 4 & 2(-2)^n + 2 & -2 \\ -6 & -3 & 3 \end{pmatrix}$$

- **当 $n = 0$ 时**，$A^0 = I = \begin{pmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & 1 \end{pmatrix}$。

**3. 求 $x_n, y_n, z_n$**

由 $\alpha_n = A^n \alpha_0$，且初始状态 $\alpha_0 = (-1, 0, 2)^T$。

- **当 $n \ge 1$ 时**：
$$\alpha_n = \begin{pmatrix} -(-2)^n - 4 & -(-2)^n - 2 & 2 \\ 2(-2)^n + 4 & 2(-2)^n + 2 & -2 \\ -6 & -3 & 3 \end{pmatrix} \begin{pmatrix} -1 \\ 0 \\ 2 \end{pmatrix} = \begin{pmatrix} (-2)^n + 8 \\ -2(-2)^n - 8 \\ 12 \end{pmatrix}$$
即：
$$x_n = (-2)^n + 8$$
$$y_n = -2(-2)^n - 8$$
$$z_n = 12$$

- **当 $n = 0$ 时**：
直接由初始条件给出：
$$x_0 = -1,\quad y_0 = 0,\quad z_0 = 2$$
（注：若将 $n=0$ 错误代入 $n \ge 1$ 的公式会得到 $x_0=9, y_0=-10, z_0=12$，这正是由于未区分 $0^0=1$ 与 $0^n=0\ (n\ge1)$ 导致的，因此必须单独说明 $n=0$ 的情况。）

> 回答核对：部分公式或数值尚无确定性核验依据，请核对后使用。