<template>
  <div id="layout">
    <header class="nav-header">
      <div class="nav-inner">
        <router-link to="/" class="nav-brand">
          Engineering Metrics
        </router-link>
        <nav class="nav-links">
          <router-link to="/" class="nav-link">Overview</router-link>
          <router-link to="/comparison" class="nav-link">Comparison</router-link>
        </nav>
      </div>
    </header>

    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
#layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.nav-header {
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
}

.nav-inner {
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 1.5rem;
  height: 52px;
  display: flex;
  align-items: center;
  gap: 2rem;
}

.nav-brand {
  font-size: 1rem;
  font-weight: 700;
  color: var(--text-primary);
  text-decoration: none;
  white-space: nowrap;
}

.nav-links {
  display: flex;
  gap: 1rem;
}

.nav-link {
  color: var(--text-muted);
  text-decoration: none;
  font-size: 0.875rem;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  transition: color 0.15s;
}

.nav-link:hover,
.nav-link.router-link-active {
  color: var(--text-primary);
}

.main-content {
  flex: 1;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
  padding: 1.5rem;
}
</style>
