import { useEffect, useState } from 'react';
import { getAuthenticatedBlob, getAuthenticatedText } from '../api/client';

type AuthenticatedBlobState = {
  url: string;
  loading: boolean;
  error: string;
};

async function authenticatedHtmlBlob(path: string, signal: AbortSignal, childUrls: string[]): Promise<Blob> {
  const html = await getAuthenticatedText(path, signal);
  const documentNode = new DOMParser().parseFromString(html, 'text/html');
  const apiImages = Array.from(documentNode.querySelectorAll<HTMLImageElement>('img[src]')).filter((image) => {
    try {
      return new URL(image.getAttribute('src') || '', window.location.origin).pathname.startsWith('/api/');
    } catch {
      return false;
    }
  });

  await Promise.all(apiImages.map(async (image) => {
    const source = image.getAttribute('src') || '';
    const asset = await getAuthenticatedBlob(source, signal);
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    const assetUrl = URL.createObjectURL(asset);
    childUrls.push(assetUrl);
    image.setAttribute('src', assetUrl);
  }));

  const csp = documentNode.querySelector<HTMLMetaElement>('meta[http-equiv="Content-Security-Policy" i]');
  if (csp) csp.content = csp.content.replace(/img-src ([^;]+)/, (_match, sources) => `img-src ${sources} blob:`);
  return new Blob([`<!doctype html>\n${documentNode.documentElement.outerHTML}`], { type: 'text/html;charset=utf-8' });
}

export function useAuthenticatedBlobUrl(path: string, kind: 'binary' | 'html' = 'binary'): AuthenticatedBlobState {
  const [state, setState] = useState<AuthenticatedBlobState>({ url: '', loading: false, error: '' });

  useEffect(() => {
    if (!path) {
      setState({ url: '', loading: false, error: '' });
      return;
    }

    const controller = new AbortController();
    let objectUrl = '';
    const childUrls: string[] = [];
    let active = true;
    setState({ url: '', loading: true, error: '' });

    const loadBlob = kind === 'html'
      ? authenticatedHtmlBlob(path, controller.signal, childUrls)
      : getAuthenticatedBlob(path, controller.signal);
    void loadBlob.then((blob) => {
      if (!active) return;
      if (typeof URL.createObjectURL !== 'function') throw new Error('当前环境不支持本地资源预览');
      objectUrl = URL.createObjectURL(blob);
      setState({ url: objectUrl, loading: false, error: '' });
    }).catch((error) => {
      if (!active || controller.signal.aborted) return;
      childUrls.splice(0).forEach((url) => URL.revokeObjectURL(url));
      setState({ url: '', loading: false, error: error instanceof Error ? error.message : String(error) });
    });

    return () => {
      active = false;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      childUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [kind, path]);

  return state;
}
