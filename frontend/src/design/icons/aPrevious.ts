import type { Shape } from './geometry';

/** Frozen first exploration, for the A hierarchy comparison only. */
export const aPrevious: Record<string, Shape> = {
  compose: { paths: [['M3 3h13v18H3zM6 7h6M6 11h3M12 16h9M17 12v9']] },
  verify: { paths: [['M7 3H3v18h4M17 3h4v18h-4M7 9h8M7 13h5M11 18l3 3 6-6']] },
  retrieve: { paths: [['M3 3h13v7M3 3v18h9M6 7h7M6 11h4M19 19l3 3'], ['M20 15a5 5 0 1 1-10 0 5 5 0 0 1 10 0Z']] },
  extract: { paths: [['M3 3h12v18H3zM6 7h6M6 11h6M6 15h3M15 12h7m-3-3 3 3-3 3'], ['M19 19h3v3h-3z', true]] },
  mistakes: { paths: [['M4 3h16v18H4zM8 7l4 4M12 7l-4 4M8 16h3l5-5']] },
};
