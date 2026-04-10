'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Camera, Upload, ArrowRight, Sparkles, Home, LogOut, User, Settings, Heart, Trash2, Eye, EyeOff } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function PalmistryApp() {
  const [currentPage, setCurrentPage] = useState('landing');
  const [tokens, setTokens] = useState(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('auth_tokens');
      return stored ? JSON.parse(stored) : null;
    }
    return null;
  });
  const [user, setUser] = useState(null);
  const [readings, setReadings] = useState([]);
  
  const [cameraStream, setCameraStream] = useState(null);
  const [capturedImage, setCapturedImage] = useState(null);
  const [reading, setReading] = useState(null);
  const [loading, setLoading] = useState(false);
  
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  
  // Auth state
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [username, setUsername] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [authError, setAuthError] = useState('');

  useEffect(() => {
    if (tokens) {
      loadUserProfile();
    }
  }, [tokens]);

  // AUTHENTICATION FUNCTIONS
  const loadUserProfile = async () => {
    try {
      const response = await fetch(`${API_URL}/users/me`, {
        headers: { 'Authorization': `Bearer ${tokens.access_token}` }
      });
      
      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
      } else if (response.status === 401) {
        localStorage.removeItem('auth_tokens');
        setTokens(null);
      }
    } catch (error) {
      console.error('Error loading profile:', error);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setAuthError('');
    setLoading(true);

    try {
      const response = await fetch(`${API_URL}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, username, password, full_name: username })
      });

      const data = await response.json();

      if (response.ok) {
        localStorage.setItem('auth_tokens', JSON.stringify(data));
        setTokens(data);
        setCurrentPage('dashboard');
        setEmail('');
        setPassword('');
        setUsername('');
      } else {
        setAuthError(data.detail || 'Registration failed');
      }
    } catch (error) {
      setAuthError('Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setAuthError('');
    setLoading(true);

    try {
      const response = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      const data = await response.json();

      if (response.ok) {
        localStorage.setItem('auth_tokens', JSON.stringify(data));
        setTokens(data);
        setCurrentPage('dashboard');
        setEmail('');
        setPassword('');
      } else {
        setAuthError(data.detail || 'Login failed');
      }
    } catch (error) {
      setAuthError('Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('auth_tokens');
    setTokens(null);
    setUser(null);
    setReadings([]);
    setCurrentPage('landing');
  };

  // CAMERA FUNCTIONS
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
    if (!capturedImage || !tokens) return;
    
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/analyze-palm-auth`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${tokens.access_token}`
        },
        body: JSON.stringify({ image: capturedImage, language: 'en' })
      });
      
      const data = await response.json();
      
      if (response.ok) {
        setReading(data);
        setCurrentPage('reading');
        loadUserReadings();
      } else {
        alert('Analysis failed: ' + (data.detail || 'Unknown error'));
      }
    } catch (error) {
      alert('Error analyzing palm: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  const loadUserReadings = async () => {
    if (!tokens) return;
    
    try {
      const response = await fetch(`${API_URL}/readings?limit=10`, {
        headers: { 'Authorization': `Bearer ${tokens.access_token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setReadings(data.readings);
      }
    } catch (error) {
      console.error('Error loading readings:', error);
    }
  };

  const toggleFavorite = async (readingId) => {
    if (!tokens) return;
    
    try {
      await fetch(`${API_URL}/readings/${readingId}/favorite`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${tokens.access_token}` }
      });
      
      setReadings(readings.map(r => 
        r.id === readingId ? { ...r, is_favorite: !r.is_favorite } : r
      ));
    } catch (error) {
      console.error('Error toggling favorite:', error);
    }
  };

  const deleteReading = async (readingId) => {
    if (!tokens || !confirm('Delete this reading?')) return;
    
    try {
      await fetch(`${API_URL}/readings/${readingId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${tokens.access_token}` }
      });
      
      setReadings(readings.filter(r => r.id !== readingId));
    } catch (error) {
      console.error('Error deleting reading:', error);
    }
  };

  const resetApp = () => {
    setCapturedImage(null);
    setReading(null);
    stopCamera();
    setCurrentPage('dashboard');
  };

  // LOGIN PAGE
  if (!tokens && currentPage === 'landing') {
    const [isLogin, setIsLogin] = useState(true);

    return (
      <div className="min-h-screen overflow-hidden" style={{
        background: 'linear-gradient(135deg, #0f0c29 0%, #1a0e4a 25%, #16213e 50%, #0f3460 75%, #16213e 100%)',
      }}>
        <div className="min-h-screen flex items-center justify-center px-4">
          <div className="w-full max-w-md">
            <div className="text-center mb-8">
              <div className="flex items-center justify-center gap-2 mb-4">
                <Sparkles className="w-8 h-8" style={{ color: '#ffd700' }} />
                <h1 className="text-3xl font-bold" style={{ color: '#ffd700' }}>Hastrekha</h1>
              </div>
              <p style={{ color: '#b0b0b0' }}>Ancient wisdom meets modern AI</p>
            </div>

            <div className="rounded-2xl p-8 backdrop-blur-sm" style={{
              background: 'rgba(255,215,0,0.08)',
              border: '1px solid rgba(255,215,0,0.2)'
            }}>
              <h2 className="text-2xl font-bold mb-6 text-center" style={{ color: '#ffd700' }}>
                {isLogin ? 'Welcome Back' : 'Join Hastrekha'}
              </h2>

              {authError && (
                <div className="mb-4 p-3 rounded-lg bg-red-500/20 border border-red-500/50">
                  <p style={{ color: '#ff6b6b' }} className="text-sm">{authError}</p>
                </div>
              )}

              <form onSubmit={isLogin ? handleLogin : handleRegister} className="space-y-4">
                {!isLogin && (
                  <div>
                    <label style={{ color: '#e0e0e0' }} className="block text-sm mb-2">Username</label>
                    <input
                      type="text"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      placeholder="Choose a username"
                      className="w-full px-4 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder-white/50 focus:outline-none focus:border-yellow-500"
                      required
                    />
                  </div>
                )}

                <div>
                  <label style={{ color: '#e0e0e0' }} className="block text-sm mb-2">Email</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="your@email.com"
                    className="w-full px-4 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder-white/50 focus:outline-none focus:border-yellow-500"
                    required
                  />
                </div>

                <div>
                  <label style={{ color: '#e0e0e0' }} className="block text-sm mb-2">Password</label>
                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full px-4 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder-white/50 focus:outline-none focus:border-yellow-500"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 transform -translate-y-1/2"
                      style={{ color: '#ffd700' }}
                    >
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full py-2 rounded-lg font-semibold transition-all mt-6"
                  style={{
                    background: 'linear-gradient(135deg, #ffd700 0%, #ffed4e 100%)',
                    color: '#0f0c29'
                  }}
                >
                  {loading ? 'Loading...' : (isLogin ? 'Login' : 'Create Account')}
                </button>
              </form>

              <div className="mt-6 text-center">
                <p style={{ color: '#b0b0b0' }} className="text-sm">
                  {isLogin ? "Don't have an account? " : 'Already have an account? '}
                  <button
                    onClick={() => {
                      setIsLogin(!isLogin);
                      setAuthError('');
                    }}
                    style={{ color: '#ffd700' }}
                    className="font-semibold hover:underline"
                  >
                    {isLogin ? 'Sign up' : 'Login'}
                  </button>
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // DASHBOARD
  if (tokens && currentPage === 'dashboard') {
    return (
      <div className="min-h-screen overflow-hidden" style={{
        background: 'linear-gradient(135deg, #0f0c29 0%, #1a0e4a 25%, #16213e 50%, #0f3460 75%, #16213e 100%)',
      }}>
        <div className="flex justify-between items-center px-6 py-4 border-b border-yellow-600/20">
          <div className="flex items-center gap-2">
            <Sparkles className="w-6 h-6" style={{ color: '#ffd700' }} />
            <h1 className="text-xl font-bold" style={{ color: '#ffd700' }}>Hastrekha</h1>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 px-4 py-2 rounded-lg transition-all"
            style={{
              background: 'rgba(255,215,0,0.1)',
              color: '#ffd700',
              border: '1px solid rgba(255,215,0,0.3)'
            }}
          >
            <LogOut size={16} />
            Logout
          </button>
        </div>

        <div className="px-6 py-12 max-w-6xl mx-auto">
          <h2 className="text-4xl font-bold mb-2" style={{
            background: 'linear-gradient(135deg, #ffd700 0%, #ffed4e 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text'
          }}>
            Welcome, {user?.full_name || user?.username}
          </h2>
          <p style={{ color: '#b0b0b0' }}>
            {user?.subscription_tier === 'free' ? '5' : '50'} readings/month • {user?.readings_this_month || 0} used this month
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 my-12">
            <button
              onClick={startCamera}
              className="p-8 rounded-xl text-left transition-all hover:scale-105"
              style={{
                background: 'linear-gradient(135deg, #ffd700 0%, #ffed4e 100%)',
                color: '#0f0c29'
              }}
            >
              <Camera className="w-8 h-8 mb-4" />
              <h3 className="text-xl font-bold">New Reading</h3>
              <p className="text-sm opacity-80">Analyze your palm now</p>
            </button>

            <div className="p-8 rounded-xl" style={{
              background: 'rgba(255,215,0,0.08)',
              border: '1px solid rgba(255,215,0,0.2)'
            }}>
              <div className="text-3xl font-bold mb-2" style={{ color: '#ffd700' }}>
                {readings.length}
              </div>
              <p style={{ color: '#e0e0e0' }}>Total Readings</p>
            </div>
          </div>

          <h3 className="text-2xl font-bold mb-6" style={{ color: '#ffd700' }}>Recent Readings</h3>
          
          {readings.length === 0 ? (
            <div className="text-center py-12" style={{ color: '#808080' }}>
              <p>No readings yet. Scan your palm to get started!</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {readings.map((r) => (
                <div
                  key={r.id}
                  className="p-4 rounded-lg border cursor-pointer hover:scale-105 transition-all"
                  style={{
                    background: 'rgba(255,215,0,0.05)',
                    borderColor: 'rgba(255,215,0,0.2)'
                  }}
                  onClick={() => {
                    setReading(r);
                    setCurrentPage('reading');
                  }}
                >
                  <div className="flex justify-between items-start mb-3">
                    <div>
                      <h4 style={{ color: '#ffd700' }} className="font-bold">{r.title || 'Reading'}</h4>
                      <p style={{ color: '#b0b0b0' }} className="text-sm">
                        {new Date(r.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleFavorite(r.id);
                        }}
                      >
                        <Heart
                          size={18}
                          style={{ color: '#ffd700' }}
                          fill={r.is_favorite ? '#ffd700' : 'none'}
                        />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteReading(r.id);
                        }}
                        style={{ color: '#ff6b6b' }}
                      >
                        <Trash2 size={18} />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
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
            Place your hand in good lighting
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
                setCurrentPage('dashboard');
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
            {capturedImage && (
              <img src={capturedImage} alt="Captured palm" className="w-full" />
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <button
              onClick={() => {
                setCapturedImage(null);
                setCurrentPage('dashboard');
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
              {loading ? (
                <span>Analyzing...</span>
              ) : (
                <>
                  <Sparkles className="w-5 h-5" />
                  Analyze Palm
                </>
              )}
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
