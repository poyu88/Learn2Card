import { ChangeEvent, useEffect, useMemo, useState } from "react";
import {
  DEFAULT_DEBUG,
  DEFAULT_MAX_BULLETS,
  DEFAULT_MAX_TOPICS,
  DEFAULT_TOPIC_THRESHOLD,
  clampMaxBullets,
  clampMaxTopics,
  clampTopicThreshold,
  isAllowedTextFile,
  loadDeckFromPublic,
  processText,
  readFileAsText,
} from "./api";
import { Card, Deck, Topic } from "./types";
import "./App.css";

type TopicFilter = "all" | string;

type StatusTone = "info" | "success" | "error";

interface StatusMessage {
  tone: StatusTone;
  text: string;
}

const emptyDeck: Deck = {
  paragraphs: [],
  topics: [],
  cards: [],
  stats: {
    paragraphCount: 0,
    topicCount: 0,
    cardCount: 0,
  },
};

const App = () => {
  const [deck, setDeck] = useState<Deck>(emptyDeck);
  const [deckLoading, setDeckLoading] = useState(true);
  const [currentTopicId, setCurrentTopicId] = useState<TopicFilter>("all");
  const [currentCardIndex, setCurrentCardIndex] = useState(0);

  const [inputText, setInputText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);

  const [topicThreshold, setTopicThreshold] = useState(DEFAULT_TOPIC_THRESHOLD);
  const [maxTopics, setMaxTopics] = useState(DEFAULT_MAX_TOPICS);
  const [maxBullets, setMaxBullets] = useState(DEFAULT_MAX_BULLETS);
  const [debug, setDebug] = useState(DEFAULT_DEBUG);
  const [paramHint, setParamHint] = useState<string | null>(null);

  const [isGenerating, setIsGenerating] = useState(false);
  const [status, setStatus] = useState<StatusMessage | null>(null);
  const [canRetry, setCanRetry] = useState(false);
  const [lastRequestText, setLastRequestText] = useState<string | null>(null);

  const applyDeck = (nextDeck: Deck) => {
    setDeck(nextDeck);
    setCurrentTopicId("all");
    setCurrentCardIndex(0);
  };

  const reloadDeck = async (successMessage?: string) => {
    const result = await loadDeckFromPublic();
    if (!result.ok) {
      setStatus({ tone: "error", text: result.error });
      return false;
    }
    applyDeck(result.deck);
    if (successMessage) {
      setStatus({ tone: "success", text: successMessage });
    }
    return true;
  };

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      setDeckLoading(true);
      const result = await loadDeckFromPublic();
      if (cancelled) return;

      if (!result.ok) {
        setStatus({ tone: "error", text: result.error });
        setDeck(emptyDeck);
      } else {
        applyDeck(result.deck);
      }
      setDeckLoading(false);
    };

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  const visibleCards = useMemo(() => {
    if (currentTopicId === "all") {
      return deck.cards;
    }
    return deck.cards.filter((card: Card) => card.topicId === currentTopicId);
  }, [currentTopicId, deck.cards]);

  const totalCards = visibleCards.length;
  const currentCard = visibleCards[currentCardIndex];

  useEffect(() => {
    if (currentCardIndex > 0 && currentCardIndex >= totalCards) {
      setCurrentCardIndex(Math.max(totalCards - 1, 0));
    }
  }, [currentCardIndex, totalCards]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select" || target?.isContentEditable) {
        return;
      }

      if (event.key === "ArrowLeft") {
        event.preventDefault();
        setCurrentCardIndex((prev) => Math.max(prev - 1, 0));
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        setCurrentCardIndex((prev) =>
          totalCards === 0 ? 0 : Math.min(prev + 1, totalCards - 1),
        );
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [totalCards]);

  const resolveTopicTitle = () => {
    if (currentTopicId === "all" && !currentCard) {
      return "全部主題";
    }
    const topicId =
      currentTopicId === "all" ? currentCard?.topicId : currentTopicId;
    const topic = deck.topics.find((item: Topic) => item.id === topicId);
    return topic?.title || "未命名主題";
  };

  const handleTopicChange = (topicId: TopicFilter) => {
    setCurrentTopicId(topicId);
    setCurrentCardIndex(0);
  };

  const handlePrev = () => {
    setCurrentCardIndex((prev) => Math.max(prev - 1, 0));
  };

  const handleNext = () => {
    setCurrentCardIndex((prev) => Math.min(prev + 1, totalCards - 1));
  };

  const disablePrev = totalCards === 0 || currentCardIndex === 0;
  const disableNext = totalCards === 0 || currentCardIndex >= totalCards - 1;

  const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    if (!isAllowedTextFile(file)) {
      setStatus({
        tone: "error",
        text: "檔案格式錯誤：僅接受 .txt 或 .md 檔案。",
      });
      setCanRetry(false);
      return;
    }

    try {
      const content = await readFileAsText(file);
      setInputText(content);
      setFileName(file.name);
      setStatus({
        tone: "info",
        text: `已讀取檔案「${file.name}」，可調整參數後點擊「生成卡片」。`,
      });
      setCanRetry(false);
    } catch (error) {
      setStatus({
        tone: "error",
        text: error instanceof Error ? error.message : "讀取檔案失敗，請再試一次。",
      });
      setCanRetry(false);
    }
  };

  const normalizeParams = () => {
    const hints: string[] = [];
    const nextThreshold = clampTopicThreshold(topicThreshold);
    const nextMaxTopics = clampMaxTopics(maxTopics);
    const nextMaxBullets = clampMaxBullets(maxBullets);

    if (nextThreshold !== topicThreshold) {
      hints.push(`分群閾值超出 0.0–1.0，已改用 ${nextThreshold}`);
      setTopicThreshold(nextThreshold);
    }
    if (nextMaxTopics !== maxTopics) {
      hints.push(`最大主題數超出 1–10，已改用 ${nextMaxTopics}`);
      setMaxTopics(nextMaxTopics);
    }
    if (nextMaxBullets !== maxBullets) {
      hints.push(`每卡摘要數超出 1–5，已改用 ${nextMaxBullets}`);
      setMaxBullets(nextMaxBullets);
    }

    setParamHint(hints.length > 0 ? hints.join("；") : null);

    return {
      topic_threshold: nextThreshold,
      max_topics: nextMaxTopics,
      max_bullets: nextMaxBullets,
      debug,
    };
  };

  const runGenerate = async (textOverride?: string) => {
    const text = (textOverride ?? inputText).trim();
    if (!text) {
      setStatus({
        tone: "error",
        text: "請先上傳 .txt/.md 檔案，或在文字框貼上內容後再生成。",
      });
      setCanRetry(false);
      return;
    }

    const params = normalizeParams();
    setIsGenerating(true);
    setCanRetry(false);
    setLastRequestText(text);
    setStatus({ tone: "info", text: "正在生成卡片，請稍候…" });

    const result = await processText({
      text,
      ...params,
    });

    if (!result.ok) {
      setStatus({ tone: "error", text: result.error });
      setCanRetry(result.canRetry);
      setIsGenerating(false);
      return;
    }

    if (result.deck) {
      applyDeck(result.deck);
      setStatus({ tone: "success", text: result.message });
    } else {
      const reloaded = await reloadDeck(result.message);
      if (!reloaded) {
        setStatus({
          tone: "error",
          text: "Backend 已完成處理，但重新載入 deck.json 失敗。",
        });
        setCanRetry(true);
      }
    }

    setIsGenerating(false);
  };

  const handleRetry = () => {
    if (!lastRequestText) return;
    void runGenerate(lastRequestText);
  };

  return (
    <div className="app">
      <div className="app-shell">
        <header className="app-header">
          <div className="app-title">文件歸納切卡機</div>
          <div className="app-subtitle">資料來源：public/deck.json（可透過 Backend API 更新）</div>
        </header>

        <section className="input-panel panel">
          <div className="panel-title">上傳檔案或輸入文字</div>

          <div className="input-grid">
            <div className="field-group">
              <label className="field-label" htmlFor="file-input">
                檔案上傳（僅 .txt / .md）
              </label>
              <input
                id="file-input"
                type="file"
                accept=".txt,.md,text/plain,text/markdown"
                onChange={handleFileChange}
                disabled={isGenerating}
              />
              {fileName ? (
                <div className="field-hint">目前檔案：{fileName}</div>
              ) : (
                <div className="field-hint">未選擇檔案時也可直接貼上文字</div>
              )}
            </div>

            <div className="field-group field-group-wide">
              <label className="field-label" htmlFor="text-input">
                文字內容
              </label>
              <textarea
                id="text-input"
                className="text-input"
                value={inputText}
                onChange={(event) => {
                  setInputText(event.target.value);
                  setFileName(null);
                }}
                placeholder="在此貼上 Markdown 或純文字內容…"
                rows={8}
                disabled={isGenerating}
              />
            </div>
          </div>

          <div className="params-block">
            <div className="panel-subtitle">Backend 處理參數（可選）</div>
            <div className="params-grid">
              <div className="field-group">
                <label className="field-label" htmlFor="topic-threshold">
                  分群閾值：{topicThreshold.toFixed(2)}
                </label>
                <input
                  id="topic-threshold"
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={topicThreshold}
                  onChange={(event) =>
                    setTopicThreshold(Number(event.target.value))
                  }
                  disabled={isGenerating}
                />
                <div className="field-hint">相似度閾值，數值越高分群越細（0.0–1.0）</div>
              </div>

              <div className="field-group">
                <label className="field-label" htmlFor="max-topics">
                  最大主題數
                </label>
                <input
                  id="max-topics"
                  type="number"
                  min={1}
                  max={10}
                  value={maxTopics}
                  onChange={(event) => setMaxTopics(Number(event.target.value))}
                  disabled={isGenerating}
                />
                <div className="field-hint">最多產生幾個主題（1–10）</div>
              </div>

              <div className="field-group">
                <label className="field-label" htmlFor="max-bullets">
                  每卡摘要數
                </label>
                <input
                  id="max-bullets"
                  type="number"
                  min={1}
                  max={5}
                  value={maxBullets}
                  onChange={(event) => setMaxBullets(Number(event.target.value))}
                  disabled={isGenerating}
                />
                <div className="field-hint">每張卡片最多幾個要點（1–5）</div>
              </div>

              <div className="field-group checkbox-group">
                <label className="checkbox-label" htmlFor="debug-mode">
                  <input
                    id="debug-mode"
                    type="checkbox"
                    checked={debug}
                    onChange={(event) => setDebug(event.target.checked)}
                    disabled={isGenerating}
                  />
                  除錯模式
                </label>
                <div className="field-hint">顯示詳細的處理資訊</div>
              </div>
            </div>
            {paramHint ? <div className="param-warning">{paramHint}</div> : null}
          </div>

          <div className="action-row">
            <button
              type="button"
              className="primary-button"
              onClick={() => void runGenerate()}
              disabled={isGenerating}
            >
              {isGenerating ? "生成中…" : "生成卡片"}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void reloadDeck("已重新載入卡片資料。")}
              disabled={isGenerating || deckLoading}
            >
              重新載入卡片
            </button>
            {canRetry ? (
              <button
                type="button"
                className="secondary-button"
                onClick={handleRetry}
                disabled={isGenerating}
              >
                重試
              </button>
            ) : null}
          </div>

          {isGenerating ? (
            <div className="loading-row" role="status" aria-live="polite">
              <span className="spinner" aria-hidden="true" />
              <span>正在呼叫 Backend API 處理文字…</span>
            </div>
          ) : null}

          {status ? (
            <div className={`status-banner status-${status.tone}`} role="status">
              {status.text}
            </div>
          ) : null}
        </section>

        <div className="main-layout">
          <aside className="sidebar">
            <section className="panel panel-static">
              <div className="panel-title">統計資訊</div>
              <div className="stats-grid">
                <div className="stat-item">
                  <div className="stat-label">段落數</div>
                  <div className="stat-value">{deck.stats.paragraphCount}</div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">主題數</div>
                  <div className="stat-value">{deck.stats.topicCount}</div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">卡片數</div>
                  <div className="stat-value">{deck.stats.cardCount}</div>
                </div>
              </div>
            </section>

            <section className="panel">
              <div className="panel-title">主題列表</div>
              <div className="topics-list">
                <button
                  type="button"
                  className={`topic-button ${
                    currentTopicId === "all" ? "active" : ""
                  }`}
                  onClick={() => handleTopicChange("all")}
                >
                  全部主題
                </button>
                {deck.topics.map((topic: Topic) => (
                  <button
                    type="button"
                    key={topic.id}
                    className={`topic-button ${
                      currentTopicId === topic.id ? "active" : ""
                    }`}
                    onClick={() => handleTopicChange(topic.id)}
                  >
                    {topic.title || "未命名主題"}
                  </button>
                ))}
              </div>
            </section>
          </aside>

          <main className="main-panel">
            {deckLoading ? (
              <div className="empty-state">正在載入卡片資料…</div>
            ) : totalCards === 0 ? (
              <div className="empty-state">
                目前沒有卡片可顯示（可能是資料尚未產生）。
              </div>
            ) : (
              <div className="card-viewer">
                <div className="card-meta">
                  <div className="card-topic">
                    <span className="card-topic-text">{resolveTopicTitle()}</span>
                    <span className="card-counter">
                      第 {currentCardIndex + 1} 張 / 共 {totalCards} 張
                    </span>
                  </div>
                </div>

                <div className="card">
                  <h2 className="card-title">
                    {currentCard?.title || "未命名卡片"}
                  </h2>
                  {currentCard?.bullets?.length ? (
                    <ul className="card-bullets">
                      {currentCard.bullets.map((bullet: string, idx: number) => (
                        <li key={idx}>{bullet}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="card-empty">（此卡片目前沒有內容）</p>
                  )}
                </div>

                <div className="controls">
                  <button
                    type="button"
                    className="nav-button"
                    onClick={handlePrev}
                    disabled={disablePrev}
                  >
                    ← 上一張
                  </button>
                  <button
                    type="button"
                    className="nav-button"
                    onClick={handleNext}
                    disabled={disableNext}
                  >
                    下一張 →
                  </button>
                </div>
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  );
};

export default App;
