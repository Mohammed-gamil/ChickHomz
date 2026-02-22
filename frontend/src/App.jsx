import React, { useState, useRef, useEffect } from 'react'
import Header from './components/Header'
import ChatArea from './components/ChatArea'
import InputBar from './components/InputBar'
import ThemeToggle from './components/ThemeToggle'

export default function App() {
  const [dark, setDark] = useState(false)
  const [messages, setMessages] = useState([
    {
      role: 'ai',
      text: 'أهلاً وسهلاً! 🏡 أنا نور، مستشارتك الشخصية من Chic Homz. أخبريني عن غرفتك وذوقك وميزانيتك، وسأساعدك تلاقي أجمل قطع الديكور! ✨',
      products: [],
      time: new Date(),
    },
  ])
  const [loading, setLoading] = useState(false)
  const [hitlPending, setHitlPending] = useState(null)
  const chatEndRef = useRef(null)
  const threadIdRef = useRef(null)

  useEffect(() => {
    if (dark) document.body.classList.add('dark')
    else document.body.classList.remove('dark')
  }, [dark])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, hitlPending])

  const ensureThread = async () => {
    if (threadIdRef.current) return threadIdRef.current
    const res = await fetch('/threads', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    const data = await res.json()
    threadIdRef.current = data.thread_id
    return data.thread_id
  }

  // Shared SSE stream processor
  const processStream = async (res, aiMsgId) => {
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let lastAiText = ''
    let streamText = ''
    let latestProducts = []
    let hitlData = null

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const payload = line.slice(6).trim()
        if (payload === '[DONE]') break

        try {
          const state = JSON.parse(payload)

          // Token-by-token streaming from response_generator
          if (state.__token__ !== undefined) {
            streamText += state.__token__
            if (aiMsgId) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === aiMsgId
                    ? { ...m, text: streamText, progressText: '' }
                    : m
                )
              )
            }
            continue
          }

          // Progress hints — show as temporary status in the AI bubble
          if (state.__progress__ && aiMsgId) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === aiMsgId
                  ? { ...m, progressText: state.__progress__ }
                  : m
              )
            )
            continue
          }

          // HITL / clarify interrupt
          if (state.__interrupt__) {
            const interrupt = state.__interrupt__[0]
            if (interrupt?.type === 'human_review') {
              hitlData = interrupt.value
            } else if (interrupt?.type === 'clarify') {
              lastAiText = interrupt.value || ''
            }
          }

          // Only extract AI message text when NOT in HITL pending mode
          // (awaiting_human_approval = true means the response is held for review)
          if (!state.awaiting_human_approval) {
            const msgs = state.messages || []
            for (let i = msgs.length - 1; i >= 0; i--) {
              if (msgs[i].type === 'ai') {
                lastAiText = msgs[i].content || ''
                break
              }
            }
          }

          // Extract products (prefer reranked)
          const prods =
            (Array.isArray(state.reranked_products) && state.reranked_products.length > 0 && state.reranked_products) ||
            (Array.isArray(state.ranked_products) && state.ranked_products.length > 0 && state.ranked_products) ||
            null
          if (prods) latestProducts = prods

          const displayText = streamText || lastAiText
          if (displayText && aiMsgId && !hitlData) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === aiMsgId
                  ? { ...m, text: displayText, products: latestProducts, progressText: '' }
                  : m
              )
            )
          }
        } catch {
          // skip malformed
        }
      }
    }

    return { lastAiText: streamText || lastAiText, latestProducts, hitlData }
  }

  const sendMessage = async (text) => {
    if (!text.trim() || loading) return

    setMessages((prev) => [...prev, { role: 'user', text, time: new Date() }])
    setLoading(true)
    setHitlPending(null)

    const aiMsgId = Date.now()
    setMessages((prev) => [
      ...prev,
      { id: aiMsgId, role: 'ai', text: '', products: [], time: new Date(), streaming: true },
    ])

    try {
      const threadId = await ensureThread()

      const res = await fetch(`/threads/${threadId}/runs/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          input: {
            messages: [{ role: 'human', content: text }],
            raw_query: text,
          },
        }),
      })

      if (!res.ok) throw new Error(`Server error: ${res.status}`)

      const { hitlData, lastAiText } = await processStream(res, aiMsgId)

      // If HITL triggered, always remove the streaming bubble — HITL panel replaces it
      if (hitlData) {
        setMessages((prev) => prev.filter((m) => m.id !== aiMsgId))
        setHitlPending(hitlData)
      } else {
        setMessages((prev) =>
          prev.map((m) => (m.id === aiMsgId ? { ...m, streaming: false } : m))
        )
      }
    } catch (err) {
      console.error('Stream error:', err)
      setMessages((prev) =>
        prev.map((m) =>
          m.id === aiMsgId
            ? { ...m, text: 'عذراً، حدث خطأ أثناء الاتصال بالخادم. حاول مرة أخرى.', streaming: false }
            : m
        )
      )
      threadIdRef.current = null
    } finally {
      setLoading(false)
    }
  }

  // HITL approve
  const handleApprove = async (checkedFeedback) => {
    setLoading(true)
    setHitlPending(null)

    const aiMsgId = Date.now()
    setMessages((prev) => [
      ...prev,
      { id: aiMsgId, role: 'ai', text: '', products: [], time: new Date(), streaming: true, progressText: 'تم الاعتماد، جاري إرسال الرد... ✅' },
    ])

    try {
      const res = await fetch(`/threads/${threadIdRef.current}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved: true, feedback: checkedFeedback || [] }),
      })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)

      const { hitlData } = await processStream(res, aiMsgId)
      setMessages((prev) =>
        prev.map((m) => (m.id === aiMsgId ? { ...m, streaming: false } : m))
      )
      if (hitlData) setHitlPending(hitlData)
    } catch (err) {
      console.error('Approve error:', err)
      setMessages((prev) =>
        prev.map((m) =>
          m.id === aiMsgId
            ? { ...m, text: 'عذراً، حدث خطأ أثناء الاعتماد.', streaming: false }
            : m
        )
      )
    } finally {
      setLoading(false)
    }
  }

  // HITL reject
  const handleReject = async (reason) => {
    setLoading(true)
    setHitlPending(null)

    const aiMsgId = Date.now()
    setMessages((prev) => [
      ...prev,
      { id: aiMsgId, role: 'ai', text: '', products: [], time: new Date(), streaming: true, progressText: 'تم الرفض، بحاول أساعدك بشكل تاني... 🔄' },
    ])

    try {
      const res = await fetch(`/threads/${threadIdRef.current}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved: false, reason: reason || 'rejected by reviewer' }),
      })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)

      const { hitlData } = await processStream(res, aiMsgId)
      setMessages((prev) =>
        prev.map((m) => (m.id === aiMsgId ? { ...m, streaming: false } : m))
      )
      if (hitlData) setHitlPending(hitlData)
    } catch (err) {
      console.error('Reject error:', err)
      setMessages((prev) =>
        prev.map((m) =>
          m.id === aiMsgId
            ? { ...m, text: 'عذراً، حدث خطأ أثناء إعادة المحاولة.', streaming: false }
            : m
        )
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh', overflow: 'hidden' }}>
      <Header dark={dark} />
      <ChatArea
        messages={messages}
        loading={loading}
        chatEndRef={chatEndRef}
        dark={dark}
        hitlPending={hitlPending}
        onApprove={handleApprove}
        onReject={handleReject}
      />
      <InputBar onSend={sendMessage} loading={loading || !!hitlPending} dark={dark} />
      <ThemeToggle dark={dark} onToggle={() => setDark(!dark)} />
    </div>
  )
}
