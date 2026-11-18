import { useEffect, useRef, useState } from "react";

export const prefersReducedMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Marca o elemento com a classe `in` quando ele entra na tela (revelação suave, uma vez). */
export function useReveal<T extends HTMLElement>() {
  const ref = useRef<T>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (prefersReducedMotion() || !("IntersectionObserver" in window)) {
      node.classList.add("in");
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.15, rootMargin: "0px 0px -8% 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return ref;
}

/** Digita os textos em sequência, uma vez. Sem animação, devolve tudo de uma vez. */
export function useTypewriter(parts: string[], startDelay = 700, speed = 22) {
  const [typed, setTyped] = useState<string[]>(() => (prefersReducedMotion() ? parts : parts.map(() => "")));

  useEffect(() => {
    if (prefersReducedMotion()) return;
    let cancelled = false;
    const timers: number[] = [];

    const run = (partIndex: number, charIndex: number) => {
      if (cancelled || partIndex >= parts.length) return;
      const text = parts[partIndex];
      if (charIndex <= text.length) {
        setTyped((current) => current.map((value, i) => (i === partIndex ? text.slice(0, charIndex) : value)));
        timers.push(window.setTimeout(() => run(partIndex, charIndex + 1), speed));
      } else {
        timers.push(window.setTimeout(() => run(partIndex + 1, 0), partIndex === 0 ? 520 : 300));
      }
    };

    timers.push(window.setTimeout(() => run(0, 0), startDelay));
    return () => {
      cancelled = true;
      timers.forEach((id) => window.clearTimeout(id));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return typed;
}

const UPDATE_CHECK_MS = 60_000;
const RELOAD_GUARD_KEY = "aibites:reload-at";

/**
 * Recarrega a página quando o servidor passa a servir outra versão ou outro deploy, para ninguém ficar
 * com o site velho aberto. Confere a cada minuto e quando a aba volta ao primeiro plano. Se o servidor
 * estiver fora do ar (reiniciando), não faz nada; só recarrega depois de uma resposta válida diferente.
 */
export function useAutoUpdate() {
  useEffect(() => {
    let current: string | null = null;
    let stopped = false;

    const check = async () => {
      try {
        const response = await fetch("/api/health", { cache: "no-store" });
        if (!response.ok) return;
        const data = (await response.json()) as { versao?: string; build?: string };
        if (stopped || !data.versao) return;
        const id = `${data.versao}+${data.build ?? ""}`;
        if (current === null) {
          current = id;
          return;
        }
        if (id === current) return;
        // Trava contra laço de recarga (por exemplo, dois servidores com builds diferentes atrás do balanceador).
        let last = 0;
        try {
          last = Number(sessionStorage.getItem(RELOAD_GUARD_KEY) ?? 0);
          sessionStorage.setItem(RELOAD_GUARD_KEY, String(Date.now()));
        } catch {
          /* sessionStorage indisponível: segue sem a trava */
        }
        if (Date.now() - last > 30_000) window.location.reload();
      } catch {
        /* sem rede ou servidor reiniciando: tenta de novo na próxima checagem */
      }
    };

    void check();
    const timer = window.setInterval(check, UPDATE_CHECK_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void check();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);
}
