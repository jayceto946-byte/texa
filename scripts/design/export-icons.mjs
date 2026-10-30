/** Export the exact authored geometry used by the isolated React board. No raster conversion. */
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const ts = require('../../frontend/node_modules/typescript');
const source = readFileSync(resolve('frontend/src/components/icons/geometry.ts'), 'utf8') + '\n'
  + readFileSync(resolve('frontend/src/design/icons/geometry.ts'), 'utf8').replace(/^import .*;$/gm, '').replace(/^export type \{.*;$/gm, '');
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { geometry } = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'));
let count = 0;
for (const [direction, shapes] of Object.entries(geometry)) {
  const dir = resolve('docs/design/icons', direction);
  mkdirSync(dir, { recursive: true });
  for (const [name, shape] of Object.entries(shapes)) {
    for (const [suffix, paths] of [['', shape.paths], ...(shape.small ? [['-16', shape.small]] : [])]) {
      const content = `<svg xmlns="http://www.w3.org/2000/svg" width="${suffix ? 16 : 24}" height="${suffix ? 16 : 24}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="square" stroke-linejoin="miter">\n${paths.map(([d, filled]) => `  <path d="${d}"${filled ? ' fill="currentColor" stroke="none"' : ''}/>`).join('\n')}\n</svg>\n`;
      writeFileSync(resolve(dir, name + suffix + '.svg'), content);
      count++;
    }
  }
}
console.log(`${count} SVG files exported (60 base + optical variants).`);
