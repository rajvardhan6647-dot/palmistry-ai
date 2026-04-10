'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Camera, Upload, ArrowRight, Sparkles, Home, Info } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function PalmistryApp() {
  const [currentPage, setCurrentPage] = useState('landing');
  const [cameraStream, setCameraStream] = useState(null);
  const [capturedImage, setCapturedImage] = useState(null);
  const [reading, setReading] = useState(null);
  const [loading, setLoading] = useState(false);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      setCameraStream(stream);
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setCurrentPage('camera');
    } catch (error) {
      alert('Unable to access camera. Please check permissions.');
    }
  };

  const capturePhoto = () => {
    if (videoRef.current && canvasRef.current) {
      const context = canvasRef.current.getContext('2d');
      canvasRef.current.width = videoRef.current.videoWidth;
      canvasRef.current.height = videoRef.current.videoHeight;
      context.drawImage(videoRef.current, 0, 0);
      
      const imageData = canvasRef.current.toDataURL('image/jpeg', 0.95);
      setCapturedImage(imageData);
      stopCamera();
      setCurrentPage('preview');
    }
  };

  const stopCamera = () => {
    if (cameraStream) {
      cameraStream.getTracks().forEach(track => track.stop());
      setCameraStream(null);
    }
  };

  const analyzeImage = async () => {
    if (!capturedImage) return;
    
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/analyze-palm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: capturedImage, language: 'en' })
      });
      
      const data = await response.json();
      setReading(data);
      setCurrentPage('reading');
    } catch (error) {
      alert('Error analyzing palm. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const resetApp = () => {
    setCapturedImage(null);
    setReading(null);
    stopCamera();
    setCurrentPage('landing');
  };

  // LANDING PAGE
  if (currentPage === 'landing') {
    return (
      <div className="min-h-screen overflow-hidden" style={{
        background: 'linear-gradient(135deg, #0f0c29 0%, #1a0e4a 25%, #16213e 50%, #0f3460 75%, #16213e 100%)',
        backgroundAttachment: 'fixed'
      }}>
        <div className="min-h-screen flex items-center justify-center px-4">
          <div className="max-w-2xl text-center">
            <div className="mb-8">
              <div className="text-6xl font-bold mb-4" style={{ 
                background: 'linear-gradient(135deg, #ffd700 0%, #ffed4e 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text'
              }}>
                Unveil Your<br />Destiny
              </div>
              <p className="text-lg" style={{ color: '#e0e0e0' }}>
                Ancient Indian palmistry wisdom meets modern AI.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 my-12">
              {[
                { icon: '🌙', title: 'Ancient Knowledge', desc: 'Vrihud Hastrekha Shastra' },
                { icon: '🤖', title: 'AI Powered', desc: 'Advanced vision analysis' },
                { icon: '✨', title: 'Personal Insights', desc: '240+ palmistry combinations' }
              ].map((item, i) => (
                <div key={i} className="p-4 rounded-lg backdrop-blur-sm border" style={{
                  background: 'rgba(255,215,0,0.08)',
                  borderColor: 'rgba(255,215,0,0.2)'
                }}>
                  <div className="text-3xl mb-2">{item.icon}</div>
                  <h3 style={{ color: '#ffd700' }} className="font-semibold mb-1">{item.title}</h3>
                  <p className="text-sm" style={{ color: '#b0b0b0' }}>{item.desc}</p>
                </div>
              ))}
            </div>

            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <button
                onClick={startCamera}
                className="flex items-center justify-center gap-3 px-8 py-4 rounded-lg font-semibold transition-all hover:scale-105"
                style={{
                  background: 'linear-gradient(135deg, #ffd700 0%, #ffed4e 100%)',
                  color: '#0f0c29',
                  boxShadow: '0 0 30px rgba(255,215,0,0.3)'
                }}
              >
                <Camera className="w-5 h-5" />
                Scan Your Palm
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // CAMERA PAGE
  if (currentPage === 'camera') {
    return (
      <div className="min-h-screen flex items-center justify-center px-4 py-8" style={{
        background: 'linear-gradient(135deg, #0f0c29 0%, #1a0e4a 25%, #16213e 50%, #0f3460 75%, #16213e 100%)',
      }}>
        <div className="w-full max-w-2xl">
          <h2 className="text-3xl font-bold mb-2" style={{ color: '#ffd700' }}>Position Your Palm</h2>
          <p style={{ color: '#b0b0b0' }} className="mb-6">
            Place your hand in good lighting for best results.
          </p>

          <div className="relative rounded-2xl overflow-hidden border-2 mb-6" style={{ borderColor: 'rgba(255,215,0,0.4)' }}>
            <video
              ref={videoRef}
              autoPlay
              playsInline
              className="w-full"
              style={{ background: '#000' }}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <button
              onClick={() => {
                stopCamera();
                setCurrentPage('landing');
              }}
              className="py-3 rounded-lg font-semibold"
              style={{
                background: 'rgba(255,215,0,0.1)',
                color: '#ffd700',
                border: '1px solid rgba(255,215,0,0.3)'
              }}
            >
              Cancel
            </button>
            <button
              onClick={capturePhoto}
              className="py-3 rounded-lg font-semibold"
              style={{
                background: 'linear-gradient(135deg, #ffd700 0%, #ffed4e 100%)',
                color: '#0f0c29'
              }}
            >
              Capture
            </button>
          </div>
        </div>
      </div>
    );
  }

  // PREVIEW PAGE
  if (currentPage === 'preview') {
    return (
      <div className="min-h-screen flex items-center justify-center px-4 py-8" style={{
        background: 'linear-gradient(135deg, #0f0c29 0%, #1a0e4a 25%, #16213e 50%, #0f3460 75%, #16213e 100%)',
      }}>
        <div className="w-full max-w-2xl">
          <h2 className="text-3xl font-bold mb-6" style={{ color: '#ffd700' }}>Review Your Capture</h2>
          
          <div className="rounded-2xl overflow-hidden border-2 mb-6" style={{ borderColor: 'rgba(255,215,0,0.4)' }}>
            {capturedImage && <img src={capturedImage} alt="Captured palm" className="w-full" />}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <button
              onClick={() => {
                setCapturedImage(null);
                setCurrentPage('landing');
              }}
              className="py-3 rounded-lg font-semibold"
              style={{
                background: 'rgba(255,215,0,0.1)',
                color: '#ffd700',
                border: '1px solid rgba(255,215,0,0.3)'
              }}
            >
              Retake
            </button>
            <button
              onClick={analyzeImage}
              disabled={loading}
              className="py-3 rounded-lg font-semibold flex items-center justify-center gap-2"
              style={{
                background: 'linear-gradient(135deg, #ffd700 0%, #ffed4e 100%)',
                color: '#0f0c29',
                opacity: loading ? 0.7 : 1
              }}
            >
              {loading ? 'Analyzing...' : <>
                <Sparkles className="w-5 h-5" />
                Analyze Palm
              </>}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // READING PAGE
  if (currentPage === 'reading' && reading) {
    return (
      <div className="min-h-screen py-12 px-4" style={{
        background: 'linear-gradient(135deg, #0f0c29 0%, #1a0e4a 25%, #16213e 50%, #0f3460 75%, #16213e 100%)',
      }}>
        <div className="max-w-4xl mx-auto">
          <div className="mb-8 text-center">
            <h2 className="text-4xl font-bold mb-2" style={{
              background: 'linear-gradient(135deg, #ffd700 0%, #ffed4e 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text'
            }}>
              Your Palmistry Reading
            </h2>
          </div>

          <div className="rounded-2xl p-8 mb-6 backdrop-blur-sm" style={{
            background: 'rgba(255,215,0,0.08)',
            border: '2px solid rgba(255,215,0,0.2)'
          }}>
            <h3 style={{ color: '#ffd700' }} className="text-2xl font-bold mb-4">
              {reading.title || "Your Life's Journey"}
            </h3>
            <p style={{ color: '#e0e0e0' }} className="leading-relaxed text-lg">
              {reading.overview || "Analyzing your palm..."}
            </p>
          </div>

          {reading.insights && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
              {reading.insights.map((insight, index) => (
                <div key={index} className="rounded-xl p-5 backdrop-blur-sm" style={{
                  background: 'rgba(255,215,0,0.05)',
                  border: '1px solid rgba(255,215,0,0.2)'
                }}>
                  <h4 style={{ color: '#ffd700' }} className="font-bold mb-2">
                    {insight.category || `Insight ${index + 1}`}
                  </h4>
                  <p style={{ color: '#d0d0d0' }} className="text-sm">
                    {insight.description}
                  </p>
                </div>
              ))}
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <button
              onClick={resetApp}
              className="py-3 rounded-lg font-semibold"
              style={{
                background: 'rgba(255,215,0,0.1)',
                color: '#ffd700',
                border: '1px solid rgba(255,215,0,0.3)'
              }}
            >
              New Reading
            </button>
            <button
              className="py-3 rounded-lg font-semibold"
              style={{
                background: 'linear-gradient(135deg, #ffd700 0%, #ffed4e 100%)',
                color: '#0f0c29'
              }}
            >
              Save Reading
            </button>
          </div>
        </div>
      </div>
    );
  }

  return <div>Loading...</div>;
}