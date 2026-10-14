export function panelPlacement({width,mainWidth,contentTop,trayBottom,trayHeight,blockerTop}:{width:number;mainWidth:number;contentTop:number;trayBottom:number;trayHeight:number;blockerTop:number|null}) {
  const safeBottom=blockerTop===null?trayBottom-trayHeight-8:Math.min(blockerTop-8,trayBottom-trayHeight-8);
  const available=Math.max(0,safeBottom-contentTop-8);
  return {sheet:width<=760||mainWidth<392||available<320,bottom:trayBottom-safeBottom,maxHeight:Math.min(420,available)};
}
