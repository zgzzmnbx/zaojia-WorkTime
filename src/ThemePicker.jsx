import React, { useEffect, useRef, useState } from 'react';
import { CaretDown, Check } from '@phosphor-icons/react';

const palettes = [
  ['blue', 'Mantine 蓝', '#228be6'],
  ['teal', '青绿', '#0c8599'],
  ['violet', '鸢尾紫', '#7950c5'],
  ['slate', '石墨', '#52657a'],
];

export default function ThemePicker() {
  const menu = useRef(null);
  const [palette, setPalette] = useState(() => {
    try {
      const saved = localStorage.getItem('hours-palette');
      return palettes.some(([id]) => id === saved) ? saved : 'blue';
    } catch { return 'blue'; }
  });
  useEffect(() => {
    document.documentElement.dataset.palette = palette;
    try { localStorage.setItem('hours-palette', palette); } catch { /* Session selection still works. */ }
  }, [palette]);
  useEffect(() => {
    const closeOutside = event => { if (!menu.current?.contains(event.target)) menu.current?.removeAttribute('open'); };
    document.addEventListener('pointerdown', closeOutside);
    return () => document.removeEventListener('pointerdown', closeOutside);
  }, []);
  const close = () => { menu.current.removeAttribute('open'); menu.current.querySelector('summary').focus(); };
  return <details ref={menu} className="dropdown dropdown-end theme-picker" onKeyDown={event => {
    if (event.key === 'Escape') { event.preventDefault(); close(); }
  }}>
    <summary className="btn btn-ghost" aria-label="选择主题色" title="选择主题色">
      <span className="theme-swatch" aria-hidden="true" />{palettes.find(([id]) => id === palette)[1]}<CaretDown className="theme-caret" size={12} aria-hidden="true" />
    </summary>
    <ul className="dropdown-content menu bg-base-100 rounded-box shadow-sm theme-options" aria-label="主题色选项">
      {palettes.map(([id, name, color]) => <li key={id}><button type="button" aria-pressed={palette === id} onClick={() => { setPalette(id); close(); }}>
        <span className="theme-swatch" style={{background:color}} aria-hidden="true" />{name}<span className="theme-check" aria-hidden="true">{palette === id && <Check size={14}/>}</span>
      </button></li>)}
    </ul>
  </details>;
}
