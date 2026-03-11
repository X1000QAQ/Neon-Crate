'use client';
import { useEffect, useRef } from 'react';

export default function CyberParticles() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // 从 CSS 变量中读取 2077 主题色，保证与全局视觉域统一
    const styles = getComputedStyle(document.documentElement);
    const yellowOpacity =
      (styles.getPropertyValue('--yellow-color-opacity') || '#f9f00242').trim();

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    // ASCII 字符集 - 美式黑客风格
    const chars = '0123456789ABCDEF';

    // 更高密度的字符雨：缩小字号并放大列数
    const fontSize = 12;
    const columns = Math.floor((canvas.width / fontSize) * 2.2);

    // 每列的状态：Y 坐标 + 随机下落速度
    const drops: { y: number; speed: number }[] = [];
    for (let i = 0; i < columns; i++) {
      drops.push({
        y: Math.random() * -100,
        // 为每一列注入不同的初速度，制造失真感
        speed: 0.4 + Math.random() * 1.4, // 0.4 ~ 1.8
      });
    }

    // 明黄色方块粒子 - 降速至 40%
    const particles: { x: number; y: number; size: number; speed: number; opacity: number }[] = [];
    for (let i = 0; i < 60; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        size: Math.random() * 4 + 2,
        speed: (Math.random() * 3 + 1) * 0.4, // 降速至 40%
        opacity: Math.random() * 0.3 + 0.1 // 降低透明度，更深邃
      });
    }

    let animationId: number;
    const draw = () => {
      // 清空画布，保持底层壁纸可见
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // 绘制垂直降落的 ASCII 字符流 - 带有不稳定初速度
      ctx.font = `${fontSize}px monospace`;
      ctx.fillStyle = yellowOpacity; // 与 --yellow-color-opacity 保持一致
      
      for (let i = 0; i < drops.length; i++) {
        const drop = drops[i];
        const char = chars[Math.floor(Math.random() * chars.length)];
        const x = i * fontSize;
        const y = drop.y * fontSize;
        
        ctx.fillText(char, x, y);
        
        // 字符到达底部后重置到顶部，并随机刷新速度
        if (y > canvas.height && Math.random() > 0.975) {
          drop.y = Math.random() * -20;
          drop.speed = 0.4 + Math.random() * 1.4;
        }
        drop.y += drop.speed;
      }

      // 绘制明黄色方块粒子
      particles.forEach(p => {
        p.y += p.speed;
        if (p.y > canvas.height) {
          p.y = -10;
          p.x = Math.random() * canvas.width;
        }
        
        ctx.fillStyle = yellowOpacity;
        ctx.globalAlpha = p.opacity;
        ctx.fillRect(p.x, p.y, p.size, p.size);
        
        // 绘制方块拖影 - 更深邃
        ctx.fillStyle = 'rgba(0, 230, 246, 0.3)'; // 青色拖影，降低透明度
        ctx.globalAlpha = p.opacity * 0.2;
        ctx.fillRect(p.x, p.y + p.size, p.size, p.speed * 3);
      });
      
      ctx.globalAlpha = 1;
      animationId = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return <canvas ref={canvasRef} className="fixed inset-0 pointer-events-none z-0" style={{ willChange: 'transform' }} />;
}
