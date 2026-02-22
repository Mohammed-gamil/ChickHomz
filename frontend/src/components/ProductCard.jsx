import React from 'react'

export default function ProductCard({ product, dark }) {
  const border = dark ? '#2a2a2a' : '#e5e5e5'
  const imageUrl = product.cover || product.image_url || ''
  const productUrl = product.url || (product.handle ? `https://chickhomz.com/products/${product.handle}` : '#')

  const hasDiscount = product.discount_pct > 0
  const originalPrice = product.compare_price > 0 ? product.compare_price : null

  return (
    <div
      style={{
        background: dark ? '#1E1E1E' : '#fff',
        border: `1px solid ${border}`,
        borderRadius: 16,
        padding: 12,
        boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
        width: 220,
        minWidth: 220,
        overflow: 'hidden',
        transition: 'border-color 0.3s',
        flexShrink: 0,
      }}
      onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'rgba(201,146,26,0.5)')}
      onMouseLeave={(e) => (e.currentTarget.style.borderColor = border)}
    >
      {/* Image */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          aspectRatio: '4/3',
          borderRadius: 12,
          overflow: 'hidden',
          marginBottom: 10,
          background: dark ? '#262626' : '#f0f0f0',
        }}
      >
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={product.title}
            style={{ width: '100%', height: '100%', objectFit: 'cover', transition: 'transform 0.5s' }}
            onMouseEnter={(e) => (e.currentTarget.style.transform = 'scale(1.05)')}
            onMouseLeave={(e) => (e.currentTarget.style.transform = 'scale(1)')}
          />
        ) : (
          <div
            style={{
              width: '100%',
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <span className="material-icons-outlined" style={{ fontSize: 40, color: '#8A94A0' }}>
              chair
            </span>
          </div>
        )}

        {/* Discount badge */}
        {hasDiscount && (
          <div
            style={{
              position: 'absolute',
              top: 8,
              right: 8,
              background: '#C9921A',
              color: '#fff',
              fontSize: 11,
              fontWeight: 700,
              padding: '2px 7px',
              borderRadius: 999,
            }}
          >
            -{product.discount_pct}%
          </div>
        )}
      </div>

      {/* Product type tag */}
      {product.product_type && (
        <p style={{ fontSize: 11, color: '#C9921A', fontWeight: 600, marginBottom: 4 }}>
          {product.product_type}
        </p>
      )}

      {/* Title & Price */}
      <div style={{ marginBottom: 4 }}>
        <h3
          style={{
            fontWeight: 700,
            fontSize: 14,
            color: dark ? '#fff' : '#1a1a1a',
            lineHeight: 1.4,
            marginBottom: 4,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {product.title}
        </h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: '#C9921A' }}>
            {product.price?.toLocaleString('ar-EG')}
          </span>
          <span style={{ fontSize: 11, color: '#8A94A0' }}>ج.م</span>
          {originalPrice && originalPrice > product.price && (
            <span
              style={{ fontSize: 11, color: '#8A94A0', textDecoration: 'line-through' }}
            >
              {originalPrice.toLocaleString('ar-EG')}
            </span>
          )}
        </div>
      </div>

      {/* CTA */}
      <a
        href={productUrl}
        target="_blank"
        rel="noopener noreferrer"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 6,
          marginTop: 10,
          padding: '10px 0',
          borderRadius: 12,
          fontSize: 13,
          fontWeight: 700,
          background: '#C9921A',
          color: '#fff',
          border: 'none',
          boxShadow: '0 0 15px rgba(201,146,26,0.2)',
          textDecoration: 'none',
          cursor: 'pointer',
          transition: 'filter 0.2s',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.filter = 'brightness(1.1)')}
        onMouseLeave={(e) => (e.currentTarget.style.filter = 'brightness(1)')}
      >
        <span className="material-icons-round" style={{ fontSize: 16 }}>open_in_new</span>
        عرض المنتج
      </a>
    </div>
  )
}
