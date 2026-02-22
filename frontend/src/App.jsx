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
  const chatEndRef = useRef(null)
  const threadIdRef = useRef(null)

  useEffect(() => {
    if (dark) document.body.classList.add('dark')
    else document.body.classList.remove('dark')
  }, [dark])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Create a thread on demand (lazy)
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

  const sendMessage = async (text) => {
    if (!text.trim() || loading) return

    const userMsg = { role: 'user', text, time: new Date() }
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)

    const aiMsgId = Date.now()
    setMessages((prev) => [
      ...prev,
      {
        id: aiMsgId,
        role: 'ai',
        text: '',
        products: [],
        time: new Date(),
        streaming: true,
      },
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

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let lastAiText = ''
      let latestProducts = []

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

            // Extract last AI message from the messages array
            const msgs = state.messages || []
            for (let i = msgs.length - 1; i >= 0; i--) {
              if (msgs[i].type === 'ai') {
                lastAiText = msgs[i].content || ''
                break
              }
            }

            // Extract ranked products
            if (Array.isArray(state.ranked_products) && state.ranked_products.length > 0) {
              latestProducts = state.ranked_products
            }

            // Live update the AI message bubble
            if (lastAiText) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === aiMsgId
                    ? { ...m, text: lastAiText, products: latestProducts }
                    : m
                )
              )
            }
          } catch {
            // skip malformed lines
          }
        }
      }

      // Finalise — mark streaming done
      setMessages((prev) =>
        prev.map((m) =>
          m.id === aiMsgId ? { ...m, streaming: false } : m
        )
      )
    } catch (err) {
      console.error('Stream error:', err)
      setMessages((prev) =>
        prev.map((m) =>
          m.id === aiMsgId
            ? {
                ...m,
                text: 'عذراً، حدث خطأ أثناء الاتصال بالخادم. حاول مرة أخرى.',
                streaming: false,
              }
            : m
        )
      )
      // Reset thread on error so next message creates a fresh one
      threadIdRef.current = null
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh', overflow: 'hidden' }}>
      <Header dark={dark} />
      <ChatArea messages={messages} loading={loading} chatEndRef={chatEndRef} dark={dark} />
      <InputBar onSend={sendMessage} loading={loading} dark={dark} />
      <ThemeToggle dark={dark} onToggle={() => setDark(!dark)} />
    </div>
  )
}
