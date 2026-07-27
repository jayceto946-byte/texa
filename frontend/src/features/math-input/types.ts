export interface MathExpression {
  id: string;
  latex: string;
  displayMode: boolean;
}

export interface MathEditRequest {
  nonce: number;
  expression: MathExpression;
}
