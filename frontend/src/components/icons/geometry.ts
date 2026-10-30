/** Approved Texa A geometry. Shared with the exploration board; no theme colors. */
export type Mark = readonly [d: string, filled?: boolean];
export type Shape = { paths: Mark[]; small?: Mark[] };
export const texaShapes: Record<string, Shape> = {
    search: { paths: [['M16.5 16.5 21 21'], ['M18 10.5a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z']] },
    close: { paths: [['M5 5 19 19M19 5 5 19']] },
    back: { paths: [['M10 5 3 12l7 7M3 12h18']] },
    settings: { paths: [['M3 6h18M3 12h18M3 18h18'], ['M7 3h4v6H7zM14 9h4v6h-4zM6 15h4v6H6z', true]] },
    delete: { paths: [['M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7']] },
    edit: { paths: [['m4 15 12-12 5 5L9 20H4v-5ZM13 6l5 5']] },
    copy: { paths: [['M8 8h13v13H8zM16 4V3H3v13h1']] },
    learning: { paths: [['M3 4h18v13H9l-6 4V4ZM7 9h10M7 13h6']] },
    books: { paths: [['M3 4h6l3 2 3-2h6v16h-6l-3 1-3-1H3V4ZM12 6v15']] },
    exercises: { paths: [['M5 3h14v18H5zM8 8h2M13 8h3M8 12h2M13 12h3M8 16h2M13 16h3']] },
    mistakes: { paths: [['M4 3h16v18H4z'], ['M7.45 7a.45.45 0 1 1-.9 0 .45.45 0 0 1 .9 0ZM9.45 7a.45.45 0 1 1-.9 0 .45.45 0 0 1 .9 0ZM11.45 7a.45.45 0 1 1-.9 0 .45.45 0 0 1 .9 0ZM13.45 7a.45.45 0 1 1-.9 0 .45.45 0 0 1 .9 0ZM15.45 7a.45.45 0 1 1-.9 0 .45.45 0 0 1 .9 0ZM17.45 7a.45.45 0 1 1-.9 0 .45.45 0 0 1 .9 0ZM7.45 10.5a.45.45 0 1 1-.9 0 .45.45 0 0 1 .9 0ZM9.45 10.5a.45.45 0 1 1-.9 0 .45.45 0 0 1 .9 0ZM11.45 10.5a.45.45 0 1 1-.9 0 .45.45 0 0 1 .9 0ZM13.45 10.5a.45.45 0 1 1-.9 0 .45.45 0 0 1 .9 0ZM15.45 10.5a.45.45 0 1 1-.9 0 .45.45 0 0 1 .9 0ZM17.45 10.5a.45.45 0 1 1-.9 0 .45.45 0 0 1 .9 0ZM7.45 14a.45.45 0 1 1-.9 0 .45.45 0 0 1 .9 0ZM9.45 14a.45.45 0 1 1-.9 0 .45.45 0 0 1 .9 0ZM11.45 14a.45.45 0 1 1-.9 0 .45.45 0 0 1 .9 0ZM13.45 14a.45.45 0 1 1-.9 0 .45.45 0 0 1 .9 0Z', true], ['M15 12.364 16 13.364 17 12.364 17.636 13 16.636 14 17.636 15 17 15.636 16 14.636 15 15.636 14.364 15 15.364 14 14.364 13Z', true]] },
    notes: { paths: [['M5 3h14v18H5zM3 7h4M3 12h4M3 17h4M10 8h5M10 12h5']] },
    goals: { paths: [['M4 21V3h15l-3 5 3 5H4M8 7h5']] },
    retrieve: { paths: [['M3 3h13v7M3 3v18h9M6 7h7M6 11h4M19 19l3 3'], ['M20 15a5 5 0 1 1-10 0 5 5 0 0 1 10 0Z']] },
    extract: { paths: [['M4 3h16v18H4z'], ['M7 7h7M7 11h3M7 16h9m-3-3 3 3-3 3']], small: [['M4 3h16v18H4z'], ['M7 7h7M7 16h9m-3-3 3 3-3 3']] },
    verify: { paths: [['M7 3H3v18h4M17 3h4v18h-4M7 9h8M7 13h3'], ['M12 16l2 1.5 3-3.5']] },
    agent: { paths: [['M3 4h8v5H3zM3 15h8v5H3zM7 9v6M11 6h5v12h-5M16 12h5m-3-3 3 3-3 3']] },
    compose: { paths: [['M3 3h13v18H3zM6 7h6M6 11h3'], ['M8.25 16h4.5M10.5 13.75v4.5']] },
    send: { paths: [['M12 21V3M5 10l7-7 7 7']] },
    image: { paths: [['M3 4h18v16H3zM3 17l6-6 5 5 3-3 4 4'], ['M16 7h2v2h-2z', true]] },
};
