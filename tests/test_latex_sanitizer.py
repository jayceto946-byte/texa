"""LaTeX 输出清洗单元测试"""
import pytest
from utils.latex_sanitizer import sanitize_latex


def test_closes_unclosed_inline_math():
    """未闭合的 $ 会把后续文字吞进数学模式导致报红，应自动补闭合。"""
    input_text = "梯度 $\\nabla f(X)$ 是下降最快的方向。"
    # 当前这个 case 是正常的；作为对照，确保不会误伤
    assert sanitize_latex(input_text) == input_text


def test_fixes_missing_closing_dollar():
    """LLM 可能漏掉行内公式结尾的 $，导致整句报红。"""
    input_text = "梯度 $\\nabla f(X) 是下降最快的方向。"
    expected = "梯度 $\\nabla f(X)$ 是下降最快的方向。"
    assert sanitize_latex(input_text) == expected


def test_converts_tex_inline_delimiters():
    """DeepSeek 有时输出 \\( ... \\) 而不是 $...$。"""
    input_text = "设 \\(x = 1\\)，则 \\(y = 2\\)。"
    expected = "设 $x = 1$，则 $y = 2$。"
    assert sanitize_latex(input_text) == expected


def test_converts_tex_display_delimiters():
    """DeepSeek 有时输出 \\[ ... \\] 而不是 $$...$$。"""
    input_text = "\\[\\nabla f(X) = 0\\]"
    expected = "$$\\nabla f(X) = 0$$"
    assert sanitize_latex(input_text) == expected


def test_does_not_break_display_math():
    """已有的 $$...$$ 不应被误处理。"""
    input_text = "$$\\begin{bmatrix}1 & 2\\\\3 & 4\\end{bmatrix}$$"
    assert sanitize_latex(input_text) == input_text


def test_keeps_balanced_inline_math_intact():
    """正常平衡的 $...$ 应原样保留。"""
    input_text = "函数 $f(x) = x^2$ 在 $x=0$ 处取极小值。"
    assert sanitize_latex(input_text) == input_text


def test_closes_unclosed_display_math():
    """$$ 开了没合会把后续内容全吞掉。"""
    input_text = "$$\\nabla f(X) = 0\n后续文字。"
    expected = "$$\\nabla f(X) = 0$$\n后续文字。"
    assert sanitize_latex(input_text) == expected


def test_strip_latex_line_spacing_option():
    input_text = r"$$\begin{aligned} a&=b\\[4pt] c&=d \end{aligned}$$"
    output = sanitize_latex(input_text)
    assert r"[4pt]" not in output
    assert r"\\" in output

def test_normalizes_fullwidth_dollar_delimiters():
    assert sanitize_latex("\uff04x=1\uff04") == "$x=1$"


def test_wraps_bare_aligned_environment():
    input_text = "step\n\\begin{aligned}a&=b\\\\c&=d\\end{aligned}\ndone"
    output = sanitize_latex(input_text)
    assert "$$\n\\begin{aligned}" in output
    assert "\\end{aligned}\n$$" in output


def test_repairs_inline_dollars_split_across_formula_paragraphs():
    input_text = "$ E(500,0)\\approx 37.005\\text{ mV}\n\nE(35,0)\\approx 2.110\\text{ mV}\n\nE(25,0)\\approx 1.496\\text{ mV} $"
    output = sanitize_latex(input_text)
    assert "$ E(500,0)\\approx 37.005\\text{ mV}$" in output
    assert "$E(35,0)\\approx 2.110\\text{ mV}$" in output
    assert "$E(25,0)\\approx 1.496\\text{ mV} $" in output


def test_wraps_bare_temperature_fragment_inside_chinese_text():
    output = sanitize_latex(r"实际温度 t=500^\circ\text{C}，仪表显示多少？")
    assert output == r"实际温度 $t=500^\circ\text{C}$，仪表显示多少？"


def test_wraps_formula_only_line_with_bare_latex_commands():
    output = sanitize_latex(r"E_{\text{disp}}=36.391\text{ mV}")
    assert output == r"$E_{\text{disp}}=36.391\text{ mV}$"


def test_does_not_add_inline_delimiters_inside_display_math():
    value = "$$\nE_{\\text{总}}=E(35,0)\n$$"
    assert sanitize_latex(value) == value


def test_removes_nested_inline_delimiters_from_existing_display_math():
    value = "$$\n$E_{\\text{总}}=E(35,0)$\n$$"
    assert sanitize_latex(value) == "$$\nE_{\\text{总}}=E(35,0)\n$$"
