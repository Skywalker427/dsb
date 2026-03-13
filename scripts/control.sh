#!/bin/bash

# DSB Backend Control Script
# Usage: ./scripts/control.sh {start|stop|restart|status}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIDFILE_API="$PROJECT_DIR/.api.pid"
PIDFILE_WORKERS="$PROJECT_DIR/.workers.pid"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Load environment variables (source so DATABASE_URL etc. are set exactly as in the file)
load_env() {
    local env_file
    if [ -n "$ENV_FILE" ] && [ -f "$PROJECT_DIR/$ENV_FILE" ]; then
        env_file="$PROJECT_DIR/$ENV_FILE"
    elif [ -f "$PROJECT_DIR/.env.production" ]; then
        env_file="$PROJECT_DIR/.env.production"
    elif [ -f "$PROJECT_DIR/.env.local" ]; then
        env_file="$PROJECT_DIR/.env.local"
    elif [ -f "$PROJECT_DIR/.env" ]; then
        env_file="$PROJECT_DIR/.env"
    else
        log_error "No environment file found (.env.production, .env.local, or .env)"
        return 1
    fi
    set -a
    # shellcheck source=/dev/null
    source "$env_file"
    set +a
    log_info "Loaded environment from $(basename "$env_file")"
}

# Check if process is running
is_running() {
    local pidfile=$1
    if [ -f "$pidfile" ]; then
        local pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            return 0  # Process is running
        else
            rm -f "$pidfile"  # Clean up stale pidfile
            return 1  # Process not running
        fi
    else
        return 1  # No pidfile
    fi
}

# Start the API server
start_api() {
    log_info "Starting DSB API server..."
    
    if is_running "$PIDFILE_API"; then
        log_warning "API server is already running (PID: $(cat "$PIDFILE_API"))"
        return 0
    fi
    
    local pids_on_port
    pids_on_port=$(lsof -ti :9000 2>/dev/null)
    if [ -n "$pids_on_port" ]; then
        log_info "Freeing port 9000 (killing existing process(es): $pids_on_port)"
        echo "$pids_on_port" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi

    cd "$PROJECT_DIR"
    source .venv/bin/activate
    export PYTHONPATH="$PROJECT_DIR"
    
    nohup uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 9000 \
        --reload \
        > "$PROJECT_DIR/api.log" 2>&1 &
    
    local api_pid=$!
    echo $api_pid > "$PIDFILE_API"
    sleep 2
    if is_running "$PIDFILE_API"; then
        log_success "API server started (PID: $api_pid)"
        log_info "API available at: http://localhost:9000"
        log_info "Documentation at: http://localhost:9000/docs"
        log_info "Logs: $PROJECT_DIR/api.log"
        return 0
    else
        log_error "Failed to start API server"
        return 1
    fi
}

# Start the workers
start_workers() {
    log_info "Starting DSB background workers..."
    
    if is_running "$PIDFILE_WORKERS"; then
        log_warning "Workers are already running (PID: $(cat "$PIDFILE_WORKERS"))"
        return 0
    fi
    
    # Activate virtual environment and start workers
    cd "$PROJECT_DIR"
    source .venv/bin/activate
    export PYTHONPATH="$PROJECT_DIR"
    
    nohup python -m app.workers.worker_runner \
        > "$PROJECT_DIR/workers.log" 2>&1 &
    
    local workers_pid=$!
    echo $workers_pid > "$PIDFILE_WORKERS"
    
    # Wait a moment and check if it started successfully
    sleep 2
    if is_running "$PIDFILE_WORKERS"; then
        log_success "Workers started (PID: $workers_pid)"
        log_info "Workers processing jobs from database queue"
        log_info "Logs: $PROJECT_DIR/workers.log"
        return 0
    else
        log_error "Failed to start workers"
        return 1
    fi
}

# Stop the API server
stop_api() {
    log_info "Stopping DSB API server..."
    
    if is_running "$PIDFILE_API"; then
        local pid=$(cat "$PIDFILE_API")
        kill "$pid"
        
        # Wait for graceful shutdown
        local count=0
        while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
            sleep 1
            count=$((count + 1))
        done
        
        if kill -0 "$pid" 2>/dev/null; then
            log_warning "Force killing API server..."
            kill -9 "$pid"
        fi
        
        rm -f "$PIDFILE_API"
        log_success "API server stopped"
    else
        log_warning "API server is not running"
    fi
}

# Stop the workers
stop_workers() {
    log_info "Stopping DSB background workers..."
    
    if is_running "$PIDFILE_WORKERS"; then
        local pid=$(cat "$PIDFILE_WORKERS")
        kill "$pid"
        
        # Wait for graceful shutdown
        local count=0
        while kill -0 "$pid" 2>/dev/null && [ $count -lt 15 ]; do
            sleep 1
            count=$((count + 1))
        done
        
        if kill -0 "$pid" 2>/dev/null; then
            log_warning "Force killing workers..."
            kill -9 "$pid"
        fi
        
        rm -f "$PIDFILE_WORKERS"
        log_success "Workers stopped"
    else
        log_warning "Workers are not running"
    fi
}

# Show status
show_status() {
    log_info "DSB Backend Status:"
    echo
    
    # API Status
    if is_running "$PIDFILE_API"; then
        local api_pid=$(cat "$PIDFILE_API")
        echo -e "  ${GREEN}● API Server${NC}    - Running (PID: $api_pid)"
        echo -e "    └─ URL: ${BLUE}http://localhost:9000${NC}"
        echo -e "    └─ Docs: ${BLUE}http://localhost:9000/docs${NC}"
    else
        echo -e "  ${RED}○ API Server${NC}    - Stopped"
    fi
    
    # Workers Status
    if is_running "$PIDFILE_WORKERS"; then
        local workers_pid=$(cat "$PIDFILE_WORKERS")
        echo -e "  ${GREEN}● Workers${NC}       - Running (PID: $workers_pid)"
        echo -e "    └─ Processing background jobs"
    else
        echo -e "  ${RED}○ Workers${NC}       - Stopped"
    fi
    
    echo
    
    # Database Status (psql expects postgresql://, not postgresql+psycopg://)
    if command -v psql >/dev/null 2>&1 && [ -n "$DATABASE_URL" ]; then
        psql_url="${DATABASE_URL/postgresql+psycopg/postgresql}"
        psql_url="${psql_url/postgresql+asyncpg/postgresql}"
        if psql "$psql_url" -c "SELECT 1;" >/dev/null 2>&1; then
            echo -e "  ${GREEN}● Database${NC}      - Connected"
        else
            echo -e "  ${RED}○ Database${NC}      - Connection failed"
        fi
    else
        echo -e "  ${YELLOW}? Database${NC}      - Unable to check (psql not found or DATABASE_URL not set)"
    fi
}

# Main script logic
case "${1:-}" in
    start)
        load_env || exit 1
        log_info "Starting DSB Backend..."
        start_api
        start_workers
        echo
        show_status
        ;;
    stop)
        log_info "Stopping DSB Backend..."
        stop_api
        stop_workers
        log_success "DSB Backend stopped"
        ;;
    restart)
        load_env || exit 1
        log_info "Restarting DSB Backend..."
        stop_api
        stop_workers
        sleep 2
        start_api
        start_workers
        echo
        show_status
        ;;
    status)
        load_env
        show_status
        ;;
    api)
        case "${2:-}" in
            start)
                load_env || exit 1
                start_api
                ;;
            stop)
                stop_api
                ;;
            restart)
                load_env || exit 1
                stop_api
                sleep 1
                start_api
                ;;
            *)
                echo "Usage: $0 api {start|stop|restart}"
                exit 1
                ;;
        esac
        ;;
    workers)
        case "${2:-}" in
            start)
                load_env || exit 1
                start_workers
                ;;
            stop)
                stop_workers
                ;;
            restart)
                load_env || exit 1
                stop_workers
                sleep 2
                start_workers
                ;;
            *)
                echo "Usage: $0 workers {start|stop|restart}"
                exit 1
                ;;
        esac
        ;;
    logs)
        case "${2:-api}" in
            api)
                if [ -f "$PROJECT_DIR/api.log" ]; then
                    tail -f "$PROJECT_DIR/api.log"
                else
                    log_error "API log file not found"
                fi
                ;;
            workers)
                if [ -f "$PROJECT_DIR/workers.log" ]; then
                    tail -f "$PROJECT_DIR/workers.log"
                else
                    log_error "Workers log file not found"
                fi
                ;;
            *)
                echo "Usage: $0 logs {api|workers}"
                exit 1
                ;;
        esac
        ;;
    *)
        echo "DSB Backend Control Script"
        echo ""
        echo "Usage: $0 {start|stop|restart|status}"
        echo ""
        echo "Commands:"
        echo "  start     - Start both API and workers"
        echo "  stop      - Stop both API and workers"
        echo "  restart   - Restart both API and workers"
        echo "  status    - Show current status"
        echo ""
        echo "Individual control:"
        echo "  api {start|stop|restart}     - Control API server only"
        echo "  workers {start|stop|restart} - Control workers only"
        echo ""
        echo "Logs:"
        echo "  logs {api|workers}  - Show live logs"
        echo ""
        exit 1
        ;;
esac