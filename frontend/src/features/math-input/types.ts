export interface MathExpression {
  id: string;
  latex: string;
  displayMode: boolean;
  referenceNumber?: number;
}

export interface MathEditRequest {
  nonce: number;
  expression: MathExpression;
}
