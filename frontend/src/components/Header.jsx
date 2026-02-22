import React from 'react'

const LOGO = 'https://ninjadevs.app/og-image.png'

export default function Header({ dark }) {
  const bg = dark ? 'rgba(18,18,18,0.92)' : 'rgba(245,245,247,0.92)'
  const border = dark ? '#2a2a2a' : '#e5e5e5'

  return (
    <header
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 20,
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        background: bg,
        borderBottom: `1px solid ${border}`,
        padding: '12px 20px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        {/* Bot avatar */}
        <div style={{ position: 'relative' }}>
          <div
            style={{
              width: 42,
              height: 42,
              borderRadius: '50%',
              background: dark ? '#2C2210' : '#FFF8ED',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: `1.5px solid #C9921A`,
              overflow: 'hidden',
            }}
          >
            <span className="material-icons-round" style={{ color: '#C9921A', fontSize: 24 }}>
              home
            </span>
          </div>
          {/* Online dot */}
          <div
            style={{
              position: 'absolute',
              bottom: 0,
              right: 0,
              width: 12,
              height: 12,
              background: '#4CAF50',
              borderRadius: '50%',
              border: `2px solid ${dark ? '#121212' : '#F5F5F7'}`,
            }}
          />
        </div>

        <div>
          <h1 style={{ fontSize: 17, fontWeight: 700, lineHeight: 1.2 }}>
            نور · مستشارة Chic Homz
          </h1>
          <p style={{ fontSize: 12, color: '#8A94A0', fontWeight: 500 }}>متصلة الآن</p>
        </div>
      </div>

      {/* Ninja Devs branding */}
      <a
        href="https://ninjadevs.app"
        target="_blank"
        rel="noopener noreferrer"
        style={{ display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none' }}
      >
        <img
          src={LOGO}
          alt="Ninja Devs"
          style={{ height: 36, borderRadius: 8, objectFit: 'contain' }}
        />
      </a>
    </header>
  )
}
