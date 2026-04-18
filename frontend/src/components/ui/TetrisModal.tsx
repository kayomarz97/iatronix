"use client";

import React, { useEffect, useRef, useState } from "react";

const COLORS = [
  null,
  "#FF0D72",
  "#0DC2FF",
  "#0DFF72",
  "#F538FF",
  "#FF8E0D",
  "#FFE138",
  "#3877FF",
  "#555555",
];

const PIECES = "ILJOTSZ";

const createPiece = (type: string): number[][] => {
  if (type === "T") return [[0, 0, 0], [1, 1, 1], [0, 1, 0]];
  if (type === "O") return [[2, 2], [2, 2]];
  if (type === "L") return [[0, 3, 0], [0, 3, 0], [0, 3, 3]];
  if (type === "J") return [[0, 4, 0], [0, 4, 0], [4, 4, 0]];
  if (type === "I") return [[0, 5, 0, 0], [0, 5, 0, 0], [0, 5, 0, 0], [0, 5, 0, 0]];
  if (type === "S") return [[0, 6, 6], [6, 6, 0], [0, 0, 0]];
  return [[7, 7, 0], [0, 7, 7], [0, 0, 0]];
};

const getRandomPiece = () => createPiece(PIECES[(PIECES.length * Math.random()) | 0]);

const createMatrix = (width: number, height: number): number[][] => {
  const matrix: number[][] = [];
  let remaining = height;
  while (remaining > 0) {
    matrix.push(new Array(width).fill(0));
    remaining -= 1;
  }
  return matrix;
};

const ControlIcon = ({ children }: { children: React.ReactNode }) => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    {children}
  </svg>
);

interface TetrisModalProps {
  onClose: () => void;
}

const TetrisModal = ({ onClose }: TetrisModalProps) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nextCanvasRef = useRef<HTMLCanvasElement>(null);
  const holdCanvasRef = useRef<HTMLCanvasElement>(null);
  const apiRef = useRef<Record<string, (() => void) | undefined>>({});
  const animationRef = useRef<number | null>(null);
  const onCloseRef = useRef(onClose);

  const [score, setScore] = useState(0);
  const [isGameOver, setIsGameOver] = useState(false);

  // Detect theme at render time
  const isDark =
    typeof document !== "undefined" &&
    document.documentElement.dataset.theme !== "light";

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const nextCanvas = nextCanvasRef.current;
    const holdCanvas = holdCanvasRef.current;
    if (!canvas || !nextCanvas || !holdCanvas) return undefined;

    const context = canvas.getContext("2d")!;
    const nextContext = nextCanvas.getContext("2d")!;
    const holdContext = holdCanvas.getContext("2d")!;
    context.setTransform(20, 0, 0, 20, 0, 0);
    nextContext.setTransform(15, 0, 0, 15, 0, 0);
    holdContext.setTransform(15, 0, 0, 15, 0, 0);

    let gameState = "IDLE";
    let arena = createMatrix(10, 20);
    const player = { pos: { x: 0, y: 0 }, matrix: null as number[][] | null, score: 0 };
    let nextPieceMatrix: number[][] | null = null;
    let holdPieceMatrix: number[][] | null = null;
    let hasHeld = false;
    let dropCounter = 0;
    let dropInterval = 1000;
    let lastTime = 0;
    let clearingLines: number[] = [];
    let clearAnimStart = 0;
    const CLEAR_ANIM_DURATION = 300;
    let gameOverAnimRow = 19;
    let gameOverAnimLastTime = 0;

    const drawMatrix = (matrix: number[][], offset: { x: number; y: number }, ctx = context) => {
      matrix.forEach((row, y) => {
        row.forEach((value, x) => {
          if (value !== 0) {
            ctx.fillStyle = COLORS[value] as string;
            ctx.fillRect(x + offset.x, y + offset.y, 1, 1);
            ctx.fillStyle = "rgba(255,255,255,0.15)";
            ctx.fillRect(x + offset.x, y + offset.y, 1, 0.08);
            ctx.fillRect(x + offset.x, y + offset.y, 0.08, 1);
            ctx.fillStyle = "rgba(0,0,0,0.3)";
            ctx.fillRect(x + offset.x, y + offset.y + 0.92, 1, 0.08);
            ctx.fillRect(x + offset.x + 0.92, y + offset.y, 0.08, 1);
          }
        });
      });
    };

    const drawPreviewCanvas = (matrix: number[][] | null, ctx: CanvasRenderingContext2D) => {
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, 4, 4);
      if (!matrix) return;
      const offsetX = (4 - matrix[0].length) / 2;
      const offsetY = (4 - matrix.length) / 2;
      drawMatrix(matrix, { x: offsetX, y: offsetY }, ctx);
    };

    const drawGrid = () => {
      context.strokeStyle = "#1a1a1a";
      context.lineWidth = 0.05;
      for (let y = 0; y < 20; y += 1) {
        for (let x = 0; x < 10; x += 1) {
          context.strokeRect(x, y, 1, 1);
        }
      }
    };

    const collide = (arenaMatrix: number[][], activePlayer: typeof player): boolean => {
      if (!activePlayer.matrix) return false;
      const [matrix, offset] = [activePlayer.matrix, activePlayer.pos];
      for (let y = 0; y < matrix.length; y += 1) {
        for (let x = 0; x < matrix[y].length; x += 1) {
          if (matrix[y][x] !== 0 && (arenaMatrix[y + offset.y] && arenaMatrix[y + offset.y][x + offset.x]) !== 0) {
            return true;
          }
        }
      }
      return false;
    };

    const merge = (arenaMatrix: number[][], activePlayer: typeof player) => {
      if (!activePlayer.matrix) return;
      activePlayer.matrix.forEach((row, y) => {
        row.forEach((value, x) => {
          if (value !== 0) {
            arenaMatrix[y + activePlayer.pos.y][x + activePlayer.pos.x] = value;
          }
        });
      });
    };

    const drawGhost = () => {
      if (!player.matrix || gameState !== "PLAYING") return;
      const ghost = { matrix: player.matrix, pos: { x: player.pos.x, y: player.pos.y }, score: 0 };
      while (!collide(arena, ghost)) ghost.pos.y += 1;
      ghost.pos.y -= 1;
      context.globalAlpha = 0.2;
      drawMatrix(ghost.matrix, ghost.pos);
      context.globalAlpha = 1;
    };

    const draw = () => {
      context.fillStyle = "#000";
      context.fillRect(0, 0, canvas.width, canvas.height);
      drawGrid();
      drawMatrix(arena, { x: 0, y: 0 });
      if (gameState === "PLAYING" && player.matrix) {
        drawGhost();
        drawMatrix(player.matrix, player.pos);
      }
      if (gameState === "CLEARING") {
        const progress = (performance.now() - clearAnimStart) / CLEAR_ANIM_DURATION;
        const alpha = Math.max(0, 1 - progress);
        context.fillStyle = `rgba(255,255,255,${alpha})`;
        clearingLines.forEach((y) => context.fillRect(0, y, 10, 1));
      }
    };

    const updateScore = () => setScore(player.score);

    const rotate = (matrix: number[][], dir = 1) => {
      for (let y = 0; y < matrix.length; y += 1) {
        for (let x = 0; x < y; x += 1) {
          [matrix[x][y], matrix[y][x]] = [matrix[y][x], matrix[x][y]];
        }
      }
      if (dir > 0) matrix.forEach((row) => row.reverse());
      else matrix.reverse();
    };

    const getFullLines = () => {
      const lines: number[] = [];
      for (let y = 0; y < arena.length; y += 1) {
        if (arena[y].every((value) => value !== 0 && value !== 8)) lines.push(y);
      }
      return lines;
    };

    const triggerGameOver = () => {
      gameState = "GAMEOVER_ANIM";
      gameOverAnimRow = arena.length - 1;
      gameOverAnimLastTime = performance.now();
      merge(arena, player);
      player.matrix = null;
    };

    const playerReset = () => {
      if (!nextPieceMatrix) nextPieceMatrix = getRandomPiece();
      player.matrix = nextPieceMatrix;
      nextPieceMatrix = getRandomPiece();
      drawPreviewCanvas(nextPieceMatrix, nextContext);
      player.pos.y = 0;
      player.pos.x = (arena[0].length / 2 | 0) - (player.matrix[0].length / 2 | 0);
      hasHeld = false;
      if (collide(arena, player)) triggerGameOver();
    };

    const processClearedLines = () => {
      const newArena = arena.filter((_, y) => !clearingLines.includes(y));
      const clearedCount = arena.length - newArena.length;
      while (newArena.length < arena.length) newArena.unshift(new Array(arena[0].length).fill(0));
      arena = newArena;
      if (clearedCount > 0) {
        let scoreAdd = 0;
        let reward = 1;
        for (let i = 0; i < clearedCount; i += 1) {
          scoreAdd += reward * 10;
          reward *= 2;
        }
        player.score += scoreAdd;
        dropInterval = Math.max(200, dropInterval - clearedCount * 20);
        updateScore();
      }
      gameState = "PLAYING";
      clearingLines = [];
      playerReset();
    };

    const playerDrop = () => {
      if (gameState !== "PLAYING") return;
      player.pos.y += 1;
      if (collide(arena, player)) {
        player.pos.y -= 1;
        merge(arena, player);
        const linesToClear = getFullLines();
        if (linesToClear.length > 0) {
          gameState = "CLEARING";
          clearingLines = linesToClear;
          clearAnimStart = performance.now();
        } else {
          playerReset();
        }
      }
      dropCounter = 0;
    };

    const playerMove = (dir: number) => {
      if (gameState !== "PLAYING") return;
      player.pos.x += dir;
      if (collide(arena, player)) player.pos.x -= dir;
    };

    const playerRotate = () => {
      if (gameState !== "PLAYING") return;
      const pos = player.pos.x;
      let offset = 1;
      rotate(player.matrix!);
      while (collide(arena, player)) {
        player.pos.x += offset;
        offset = -(offset + (offset > 0 ? 1 : -1));
        if (offset > player.matrix![0].length) {
          rotate(player.matrix!, -1);
          player.pos.x = pos;
          return;
        }
      }
    };

    const playerHardDrop = () => {
      if (gameState !== "PLAYING") return;
      while (!collide(arena, player)) player.pos.y += 1;
      player.pos.y -= 1;
      playerDrop();
    };

    const playerHold = () => {
      if (gameState !== "PLAYING" || hasHeld) return;
      if (holdPieceMatrix === null) {
        holdPieceMatrix = player.matrix;
        playerReset();
      } else {
        const temp = player.matrix;
        player.matrix = holdPieceMatrix;
        holdPieceMatrix = temp;
        player.pos.y = 0;
        player.pos.x = (arena[0].length / 2 | 0) - (player.matrix![0].length / 2 | 0);
        if (collide(arena, player)) triggerGameOver();
      }
      hasHeld = true;
      drawPreviewCanvas(holdPieceMatrix, holdContext);
    };

    const restartGame = () => {
      arena = createMatrix(10, 20);
      player.score = 0;
      player.matrix = null;
      dropInterval = 1000;
      nextPieceMatrix = null;
      holdPieceMatrix = null;
      hasHeld = false;
      clearingLines = [];
      setIsGameOver(false);
      drawPreviewCanvas(null, holdContext);
      updateScore();
      gameState = "PLAYING";
      playerReset();
      lastTime = performance.now();
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
      animationRef.current = requestAnimationFrame(update);
    };

    const update = (time = 0) => {
      if (gameState === "IDLE" || gameState === "GAMEOVER") return;
      const deltaTime = time - lastTime;
      lastTime = time;
      if (gameState === "PLAYING") {
        dropCounter += deltaTime;
        if (dropCounter > dropInterval) playerDrop();
      } else if (gameState === "CLEARING") {
        if (performance.now() - clearAnimStart >= CLEAR_ANIM_DURATION) processClearedLines();
      } else if (gameState === "GAMEOVER_ANIM") {
        if (time - gameOverAnimLastTime > 40) {
          if (gameOverAnimRow >= 0) {
            arena[gameOverAnimRow].fill(8);
            gameOverAnimRow -= 1;
            gameOverAnimLastTime = time;
          } else {
            gameState = "GAMEOVER_DELAY";
            gameOverAnimLastTime = time;
          }
        }
      } else if (gameState === "GAMEOVER_DELAY") {
        if (time - gameOverAnimLastTime > 1500) {
          gameState = "GAMEOVER";
          setIsGameOver(true);
        }
      }
      draw();
      animationRef.current = requestAnimationFrame(update);
    };

    apiRef.current = { playerMove: () => {}, playerRotate, playerDrop, playerHardDrop, playerHold, restartGame };
    // Override playerMove with dir-bound versions via the exposed API
    (apiRef.current as Record<string, unknown>).playerMoveLeft = () => playerMove(-1);
    (apiRef.current as Record<string, unknown>).playerMoveRight = () => playerMove(1);

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onCloseRef.current?.(); return; }
      if (gameState !== "PLAYING") return;
      const keyMap: Record<string, () => void> = {
        ArrowLeft: () => playerMove(-1),
        ArrowRight: () => playerMove(1),
        ArrowDown: () => playerDrop(),
        ArrowUp: () => playerRotate(),
        " ": () => playerHardDrop(),
        c: () => playerHold(),
        C: () => playerHold(),
      };
      if (keyMap[event.key]) { event.preventDefault(); keyMap[event.key](); }
    };

    document.addEventListener("keydown", handleKeyDown);
    restartGame();

    return () => {
      gameState = "IDLE";
      document.removeEventListener("keydown", handleKeyDown);
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, []);

  const shellClasses = isDark
    ? "bg-[#030712]/92 border-white/10 text-white"
    : "bg-white/92 border-gray-200 text-gray-900";
  const panelClasses = isDark
    ? "bg-white/5 border-white/10 text-white"
    : "bg-slate-50/90 border-gray-200 text-gray-900";
  const subtleText = isDark ? "text-white/45" : "text-gray-500";
  const controlButton = isDark
    ? "bg-white/10 text-white hover:bg-white/15 active:bg-white/20"
    : "bg-gray-200 text-gray-900 hover:bg-gray-300 active:bg-gray-400";
  const actionButton = isDark
    ? "bg-[#39FF14] text-black hover:bg-[#7bff63] active:bg-[#32d613]"
    : "bg-slate-800 text-white hover:bg-slate-700 active:bg-slate-600";

  return (
    <div className="fixed inset-0 z-[999999] flex items-center justify-center bg-black/80 p-4 backdrop-blur-md">
      <div className={`relative w-full max-w-4xl rounded-[2rem] border p-4 shadow-2xl sm:p-6 ${shellClasses}`}>
        <button
          type="button"
          onClick={onClose}
          className={`absolute right-4 top-4 flex h-9 w-9 items-center justify-center rounded-full border transition-colors ${
            isDark ? "border-white/10 bg-white/10 text-white hover:bg-white/15" : "border-gray-200 bg-white text-gray-900 hover:bg-gray-100"
          }`}
        >
          ✕
        </button>

        <div className="mb-6 flex items-center justify-between pr-12">
          <div>
            <h2 className="text-2xl font-black uppercase tracking-[0.35em]">Tetris</h2>
            <p className={`mt-2 text-xs font-mono uppercase tracking-[0.25em] ${subtleText}`}>
              Easter egg — you found it
            </p>
          </div>
          <button
            type="button"
            onClick={() => (apiRef.current as Record<string, unknown> & { restartGame?: () => void }).restartGame?.()}
            className={`rounded-full px-5 py-3 text-xs font-black uppercase tracking-[0.2em] transition-all ${actionButton}`}
          >
            Restart
          </button>
        </div>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_220px]">
          <div className="flex justify-center">
            <div className={`relative inline-block rounded-2xl border p-3 shadow-inner ${isDark ? "border-white/10 bg-black" : "border-gray-200 bg-white"}`}>
              <canvas ref={canvasRef} width="200" height="400" className="block" />
              {isGameOver && (
                <div className="absolute inset-0 flex flex-col items-center justify-center rounded-xl bg-black/80 backdrop-blur-sm">
                  <span className="mb-4 text-3xl font-black uppercase tracking-[0.35em] text-red-400">Game Over</span>
                  <button
                    type="button"
                    onClick={() => (apiRef.current as Record<string, unknown> & { restartGame?: () => void }).restartGame?.()}
                    className={`rounded-full px-5 py-3 text-xs font-black uppercase tracking-[0.2em] transition-all ${actionButton}`}
                  >
                    Restart
                  </button>
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <div className={`rounded-2xl border p-4 ${panelClasses}`}>
              <p className={`mb-1 text-[10px] font-mono uppercase tracking-[0.3em] ${subtleText}`}>Your Score</p>
              <div className={`font-mono text-xl ${isDark ? "text-[#39FF14]" : "text-slate-800"}`}>{score.toLocaleString()}</div>
            </div>
            <div className={`rounded-2xl border p-4 ${panelClasses}`}>
              <p className={`mb-1 text-[10px] font-mono uppercase tracking-[0.3em] ${subtleText}`}>Kayo&apos;s Score</p>
              <div className={`font-mono text-sm ${isDark ? "text-white/75" : "text-slate-700"}`}>99,999,999,999</div>
            </div>
            <div className={`rounded-2xl border p-4 ${panelClasses}`}>
              <p className={`mb-3 text-[10px] font-mono uppercase tracking-[0.3em] ${subtleText}`}>Next</p>
              <canvas ref={nextCanvasRef} width="60" height="60" className="mx-auto block rounded bg-black" />
            </div>
            <div className={`rounded-2xl border p-4 ${panelClasses}`}>
              <p className={`mb-3 text-[10px] font-mono uppercase tracking-[0.3em] ${subtleText}`}>Hold (C)</p>
              <canvas ref={holdCanvasRef} width="60" height="60" className="mx-auto block rounded bg-black" />
            </div>
          </div>
        </div>

        <div className="mx-auto mt-6 flex w-full max-w-[340px] flex-col items-center gap-4">
          <div className="flex w-full items-center justify-between px-2">
            <button type="button" onClick={() => (apiRef.current as Record<string, unknown> & { playerMoveLeft?: () => void }).playerMoveLeft?.()} className={`flex h-12 w-12 items-center justify-center rounded-full transition-all ${controlButton}`}>
              <ControlIcon><path d="M19 12H5M12 19l-7-7 7-7" /></ControlIcon>
            </button>
            <div className="flex gap-3">
              <button type="button" onClick={() => (apiRef.current as Record<string, unknown> & { playerHold?: () => void }).playerHold?.()} className={`flex h-12 w-12 items-center justify-center rounded-full transition-all ${controlButton}`}>
                <ControlIcon><path d="M19 14v5a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-5" /><path d="M12 3v11" /><path d="M9 10l3 4 3-4" /></ControlIcon>
              </button>
              <button type="button" onClick={() => (apiRef.current as Record<string, unknown> & { playerRotate?: () => void }).playerRotate?.()} className={`flex h-12 w-12 items-center justify-center rounded-full transition-all ${controlButton}`}>
                <ControlIcon><path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" /><path d="M21 3v5h-5" /></ControlIcon>
              </button>
              <button type="button" onClick={() => (apiRef.current as Record<string, unknown> & { playerDrop?: () => void }).playerDrop?.()} className={`flex h-12 w-12 items-center justify-center rounded-full transition-all ${controlButton}`}>
                <ControlIcon><path d="M12 5v14M19 12l-7 7-7-7" /></ControlIcon>
              </button>
            </div>
            <button type="button" onClick={() => (apiRef.current as Record<string, unknown> & { playerMoveRight?: () => void }).playerMoveRight?.()} className={`flex h-12 w-12 items-center justify-center rounded-full transition-all ${controlButton}`}>
              <ControlIcon><path d="M5 12h14M12 5l7 7-7 7" /></ControlIcon>
            </button>
          </div>
          <button type="button" onClick={() => (apiRef.current as Record<string, unknown> & { playerHardDrop?: () => void }).playerHardDrop?.()} className={`flex w-full items-center justify-center gap-2 rounded-2xl px-4 py-3 text-sm font-black uppercase tracking-[0.2em] transition-all ${actionButton}`}>
            <ControlIcon><path d="M12 2v14M19 9l-7 7-7-7" /><path d="M5 21h14" /></ControlIcon>
            Hard Drop
          </button>
        </div>

        <p className={`mt-4 text-center text-xs font-mono uppercase tracking-[0.22em] ${subtleText}`}>
          Arrow keys move · Up rotates · Space hard drops · C holds · Esc closes
        </p>
      </div>
    </div>
  );
};

export default TetrisModal;
