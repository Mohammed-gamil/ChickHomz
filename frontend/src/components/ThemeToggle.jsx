import React from 'react'

export default function ThemeToggle({ dark, onToggle }) {
  return (
    <button
      onClick={onToggle}
      style={{
        position: 'fixed',
        bottom: 80,
        left: 16,
        zIndex: 50,
        background: dark ? '#1E1E1E' : '#fff',
        border: `1px solid ${dark ? '#333' : '#ddd'}`,
        padding: 12,
        borderRadius: '50%',
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: dark ? '#fff' : '#1a1a1a',
        transition: 'transform 0.2s',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.transform = 'scale(1.1)')}
      onMouseLeave={(e) => (e.currentTarget.style.transform = 'scale(1)')}
    >
      <span className="material-icons-outlined" style={{ fontSize: 20 }}>
        {dark ? 'light_mode' : 'dark_mode'}
      </span>
    </button>
  )
}
