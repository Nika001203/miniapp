import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function getTelegram() {
  return window.Telegram?.WebApp;
}

async function api(path) {
  const tg = getTelegram();
  const initData = tg?.initData || "";

  const response = await fetch(`${API_URL}${path}`, {
    headers: {
      "X-Telegram-Init-Data": initData,
    },
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.detail || "Ошибка API");
  }

  return data;
}

function isVideoUrl(url) {
  if (!url) return false;
  const clean = url.toLowerCase().split("?")[0];
  return clean.endsWith(".mp4") || clean.endsWith(".webm") || clean.endsWith(".ogg");
}

function App() {
  const [me, setMe] = useState(null);
  const [viewRole, setViewRole] = useState("");
  const [sections, setSections] = useState([]);
  const [section, setSection] = useState("");
  const [items, setItems] = useState([]);
  const [item, setItem] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const tg = useMemo(() => getTelegram(), []);

  useEffect(() => {
    tg?.ready();
    tg?.expand();

    loadMe();
  }, []);

  async function loadMe() {
    try {
      setLoading(true);
      setError("");

      const data = await api("/api/me");
      setMe(data);

      if (data.has_access) {
        const firstRole = data.allowed_roles?.[0] || data.role;
        setViewRole(firstRole);
        await loadSections(firstRole);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadSections(role) {
    setSection("");
    setItems([]);
    setItem(null);

    const data = await api(`/api/sections?view_role=${encodeURIComponent(role)}`);
    setSections(data.sections || []);
  }

  async function chooseRole(role) {
    setViewRole(role);
    await loadSections(role);
  }

  async function chooseSection(sec) {
    setSection(sec);
    setItem(null);

    const data = await api(
      `/api/items?view_role=${encodeURIComponent(viewRole)}&section=${encodeURIComponent(sec)}`
    );

    setItems(data.items || []);
  }

  async function openItem(itemId) {
    const data = await api(
      `/api/item?view_role=${encodeURIComponent(viewRole)}&section=${encodeURIComponent(section)}&item_id=${encodeURIComponent(itemId)}`
    );

    setItem(data.item);
  }

  function back() {
    if (item) {
      setItem(null);
      return;
    }

    if (section) {
      setSection("");
      setItems([]);
      return;
    }
  }

  if (loading) {
    return <Screen><Card>Загружаю…</Card></Screen>;
  }

  if (error) {
    return (
      <Screen>
        <Card>
          <h1>Ошибка</h1>
          <p>{error}</p>
          <p className="muted">
            Если ты открыла это не внутри Telegram Mini App, Telegram-авторизации не будет.
          </p>
        </Card>
      </Screen>
    );
  }

  if (!me?.has_access) {
    return (
      <Screen>
        <Card>
          <h1>Нет доступа</h1>
          <p>Твой Telegram ID:</p>
          <code>{me?.telegram_user?.id}</code>
          <p className="muted">
            Добавь этот ID в лист <b>users</b> в Google Sheets.
          </p>
        </Card>
      </Screen>
    );
  }

  const roleTitles = me.role_titles || {};
  const sectionTitles = me.section_titles || {};

  return (
    <Screen>
      <header className="header">
        {(section || item) && (
          <button className="ghostButton" onClick={back}>← Назад</button>
        )}
        <div>
          <h1>База знаний</h1>
          <p>{me.role_title}</p>
        </div>
      </header>

      {!section && !item && (
        <>
          {me.allowed_roles?.length > 1 && (
            <Card>
              <h2>Смотреть как роль</h2>
              <div className="buttonGrid">
                {me.allowed_roles.map((role) => (
                  <button
                    key={role}
                    className={role === viewRole ? "button active" : "button"}
                    onClick={() => chooseRole(role)}
                  >
                    {roleTitles[role] || role}
                  </button>
                ))}
              </div>
            </Card>
          )}

          <Card>
            <h2>{roleTitles[viewRole] || viewRole}</h2>
            <p className="muted">Выбери раздел:</p>

            <div className="list">
              {sections.map((sec) => (
                <button key={sec} className="row" onClick={() => chooseSection(sec)}>
                  <span>{sectionTitles[sec] || sec}</span>
                  <span>›</span>
                </button>
              ))}

              {sections.length === 0 && <p className="muted">Материалов пока нет.</p>}
            </div>
          </Card>
        </>
      )}

      {section && !item && (
        <Card>
          <h2>{sectionTitles[section] || section}</h2>
          <p className="muted">Выбери материал:</p>

          <div className="list">
            {items.map((it) => (
              <button key={it.item_id} className="row" onClick={() => openItem(it.item_id)}>
                <span>{it.title || it.item_id}</span>
                <span>›</span>
              </button>
            ))}

            {items.length === 0 && <p className="muted">В этом разделе пока пусто.</p>}
          </div>
        </Card>
      )}

      {item && (
        <Card>
          <h2>{item.title}</h2>

          {item.body && (
            <p className="bodyText">{item.body}</p>
          )}

          {item.video_url && (
            <div className="videoBox">
              <h3>Видео</h3>

              {isVideoUrl(item.video_url) ? (
                <video controls playsInline src={item.video_url}></video>
              ) : (
                <iframe
                  src={item.video_url}
                  title="Видео"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                />
              )}
            </div>
          )}

          {item.url && (
            <a className="linkButton" href={item.url} target="_blank" rel="noreferrer">
              Открыть ссылку
            </a>
          )}
        </Card>
      )}
    </Screen>
  );
}

function Screen({ children }) {
  return <main className="screen">{children}</main>;
}

function Card({ children }) {
  return <section className="card">{children}</section>;
}

createRoot(document.getElementById("root")).render(<App />);