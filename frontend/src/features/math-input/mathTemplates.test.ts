import { describe, expect, it } from 'vitest';

import { templateToEditorLatex } from './formulaEditorUtils';
import { mathTemplateCategories, mathTemplates } from './mathTemplates';

describe('mathTemplates', () => {
  it('provides templates for every visible category', () => {
    for (const category of mathTemplateCategories) {
      expect(mathTemplates.some((template) => template.category === category.id)).toBe(true);
    }
  });

  it('uses standalone block delimiters for matrix templates', () => {
    const matrices = mathTemplates.filter((template) => template.id.startsWith('matrix-'));

    expect(matrices).toHaveLength(2);
    for (const matrix of matrices) {
      expect(matrix.value.startsWith('$$\n\\begin')).toBe(true);
      expect(matrix.value.endsWith('\\end{bmatrix}\n$$')).toBe(true);
    }
  });

  it('does not leave internal markers in editor content', () => {
    for (const template of mathTemplates) {
      const latex = templateToEditorLatex(template);
      expect(latex).not.toContain('[[selection|');
      expect(latex).not.toContain('[[cursor|');
    }
  });
});
