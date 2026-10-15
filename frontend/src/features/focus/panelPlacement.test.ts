import { expect,it } from 'vitest';
import { panelPlacement } from './panelPlacement';
it('keeps the empty-chat send button below a raised panel',()=>{const value=panelPlacement({width:1280,mainWidth:1048,contentTop:48,trayBottom:820,trayHeight:52,blockerTop:340});expect(value.sheet).toBe(true);expect(820-value.bottom).toBeLessThan(340);expect(820-value.bottom-value.maxHeight).toBeGreaterThan(48);});
it('uses a sheet when a long composer or inspector leaves too little space',()=>{expect(panelPlacement({width:1024,mainWidth:330,contentTop:48,trayBottom:768,trayHeight:52,blockerTop:120}).sheet).toBe(true);expect(panelPlacement({width:760,mainWidth:760,contentTop:48,trayBottom:820,trayHeight:56,blockerTop:null}).sheet).toBe(true);});
