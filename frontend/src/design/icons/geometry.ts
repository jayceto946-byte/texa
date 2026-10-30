/** Original geometry, authored for this exploration. Coordinates are on a 24-unit canvas.
 * Each tuple is [path, filled?]. Filled planes use currentColor; no imported paths. */
import { texaShapes } from '../../components/icons/geometry';
import type { Shape } from '../../components/icons/geometry';
export type { Mark, Shape } from '../../components/icons/geometry';
export type Direction = 'A' | 'B' | 'C';
export const geometry: Record<Direction, Record<string, Shape>> = {
  A: texaShapes,
  B: {
    search: { paths: [['M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z'], ['m14 16 2-2 6 6-2 2z', true]] },
    close: { paths: [['m6 4 6 6 6-6 2 2-6 6 6 6-2 2-6-6-6 6-2-2 6-6-6-6z', true]] },
    back: { paths: [['m3 12 8-8v6h10v4H11v6z', true]] },
    settings: { paths: [['M4 5h16M4 12h16M4 19h16'], ['M7 2h4v6H7zM14 9h4v6h-4zM6 16h4v6H6z', true]] },
    delete: { paths: [['M9 3h6v3M3 6h18'], ['M5 9h14l-1 12H6z', true]] },
    edit: { paths: [['m5 14 9-9 5 5-9 9H5z', true], ['m16 3 5 5M3 22h14']] },
    copy: { paths: [['M3 3h13v2H5v11H3zM8 8h13v13H8z', true]] },
    learning: { paths: [['M3 3h18v14H9l-6 4z'], ['M6 7h12v3H6z', true], ['M6 13h8']] },
    books: { paths: [['M3 4h7v16H3z', true], ['M13 4h8v16h-8zM16 8h2M16 12h2']] },
    exercises: { paths: [['M4 3h16v18H4z'], ['M4 3h5v18H4z', true], ['M12 7h5M12 12h5M12 17h3']] },
    mistakes: { paths: [['M4 3h16v18H4z'], ['M4 3h16v5H4z', true], ['M8 12l4 4M12 12l-4 4M16 12v6']] },
    notes: { paths: [['M4 3h16v18H4z'], ['M4 3h4v18H4z', true], ['M11 8h6M11 12h6M11 16h3']] },
    goals: { paths: [['M4 22V3M4 3h16l-4 5 4 5H4z', true]] },
    retrieve: { paths: [['M3 3h13v6M3 3v18h7'], ['M3 3h4v15H3z', true], ['M20 14a5 5 0 1 1-10 0 5 5 0 0 1 10 0ZM19 18l3 4']] },
    extract: { paths: [['M3 3h12v18H3zM15 12h7m-3-3 3 3-3 3'], ['M6 6h6v4H6zM18 18h4v4h-4z', true], ['M6 14h5M6 17h3']] },
    verify: { paths: [['M3 4h18v16H3zM7 8h8M7 12h4'], ['m12 17 2-2 2 2 5-6 2 2-7 8z', true]] },
    agent: { paths: [['M3 3h7v7H3zM3 14h7v7H3z', true], ['M13 6h4v12h-4M17 12h5m-3-3 3 3-3 3']] },
    compose: { paths: [['M3 3h13v18H3z'], ['M3 3h13v5H3z', true], ['M7 12h4M7 16h2M18 12v10M13 17h10']] },
    send: { paths: [['M3 3 22 12 3 21l4-8 8-1-8-1z', true]] },
    image: { paths: [['M3 4h18v16H3z'], ['m3 19 6-8 5 5 3-3 4 6z', true], ['M15 7h3v3h-3z', true]] },
  },
  C: {
    search: { paths: [['M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0ZM15 15l6 6']] },
    close: { paths: [['M5 5 19 19M19 5 5 19']] },
    back: { paths: [['M10 5 3 12l7 7M3 12h18']] },
    settings: { paths: [['M3 6h18M3 12h18M3 18h18'], ['M7 3h3v6H7zM14 9h3v6h-3zM6 15h3v6H6z', true]] },
    delete: { paths: [['M3 6h18M8 6V3h8v3M5 6v15h14V6M9 10v7M15 10v7']] },
    edit: { paths: [['m4 15 12-12 5 5L9 20H4v-5ZM13 6l5 5']] },
    copy: { paths: [['M8 8h13v13H8zM16 3H3v13']] },
    learning: { paths: [['M3 3h18v15H9l-6 3V3ZM7 7h10M7 11h6'], ['M3 3h2v15H3z', true]] },
    books: { paths: [['M4 3h16v18H4zM8 3v18M11 7h6M11 11h4'], ['M4 3h4v4H4z', true]] },
    exercises: { paths: [['M4 3h16v18H4zM8 3v18M11 8h6M11 15h6'], ['M4 7h4v3H4zM4 14h4v3H4z', true]] },
    mistakes: { paths: [['M4 3h16v18H4zM8 3v18M12 8l5 5M17 8l-5 5M12 17h5'], ['M4 7h4v6H4z', true]] },
    notes: { paths: [['M4 3h16v18H4zM8 3v18M11 8h6M11 12h6M11 16h3'], ['M4 14h4v4H4z', true]] },
    goals: { paths: [['M4 21V3h16l-4 5 4 5H8M4 17h8M8 3v18'], ['M4 3h4v5H4z', true]] },
    retrieve: { paths: [['M4 3h16v18H4zM8 3v18M12 7h5M12 11h5M11 16h10m-3-3 3 3-3 3'], ['M4 14h4v4H4z', true]], small: [['M4 3h16v18H4zM8 3v18M12 7h5M11 15h10m-3-3 3 3-3 3'], ['M4 13h4v4H4z', true]] },
    extract: { paths: [['M4 3h12v18H4zM8 3v18M11 7h2M11 12h9M18 9l3 3-3 3'], ['M4 6h4v4H4zM18 18h4v4h-4z', true]], small: [['M4 3h12v18H4zM8 3v18M11 11h10m-3-3 3 3-3 3'], ['M4 6h4v4H4zM18 18h4v4h-4z', true]] },
    verify: { paths: [['M4 3h16v18H4zM8 3v18M11 7h6M11 11h4M12 17l3 3 7-8'], ['M4 14h4v4H4z', true]], small: [['M4 3h16v18H4zM8 3v18M11 7h6M12 16l3 3 7-8'], ['M4 13h4v4H4z', true]] },
    agent: { paths: [['M4 3h16v18H4zM8 3v18M12 7h5M12 12h5M15 7v10h6m-3-3 3 3-3 3'], ['M4 5h4v4H4zM4 15h4v4H4z', true]], small: [['M4 3h16v18H4zM8 3v18M12 7h4v9h5m-3-3 3 3-3 3'], ['M4 5h4v4H4zM4 15h4v4H4z', true]] },
    compose: { paths: [['M4 3h16v18H4zM8 3v18M11 7h6M11 11h3M14 17h8M18 13v8'], ['M4 6h4v4H4z', true]], small: [['M4 3h16v18H4zM8 3v18M11 7h6M14 16h8M18 12v8'], ['M4 6h4v4H4z', true]] },
    send: { paths: [['M12 21V3M5 10l7-7 7 7']] },
    image: { paths: [['M3 4h18v16H3zM7 4v16M10 16l3-5 5 5'], ['M15 7h3v3h-3z', true]] },
  },
};
