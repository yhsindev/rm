#!/bin/bash
# Smart Disk Image Setup Script
# Handles multiple disk image formats (raw, qcow2, etc.)

set -e

echo "=========================================="
echo "Smart Disk Image Setup"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ This script must be run as root (use sudo)"
    echo "   sudo $0"
    exit 1
fi

# Try to find disk image
echo "Searching for disk image..."
DISK_IMAGE=""

# Common locations to check
SEARCH_PATHS=(
    "/home/usr/rm/gem5_resources/parsec.img"
    "/home/usr/rm/gem5_resources/x86-ubuntu.img"
    "/home/usr/rm/gem5_resources/*.img"
    "/home/usr/rm/*.img"
    "$HOME/gem5_resources/*.img"
)

for pattern in "${SEARCH_PATHS[@]}"; do
    for img in $pattern; do
        if [ -f "$img" ]; then
            DISK_IMAGE="$img"
            echo "✓ Found disk image: $DISK_IMAGE"
            break 2
        fi
    done
done

if [ -z "$DISK_IMAGE" ]; then
    echo ""
    echo "❌ ERROR: Could not find disk image automatically"
    echo ""
    echo "Please provide the disk image path:"
    read -p "Enter full path to disk image: " DISK_IMAGE
    
    if [ ! -f "$DISK_IMAGE" ]; then
        echo "❌ File not found: $DISK_IMAGE"
        exit 1
    fi
fi

echo ""
echo "Using disk image: $DISK_IMAGE"
echo ""

# Detect disk image format
echo "Detecting disk image format..."
IMG_TYPE=$(file "$DISK_IMAGE")
echo "File type: $IMG_TYPE"
echo ""

MOUNT_POINT="/tmp/gem5_mount_$$"
mkdir -p "$MOUNT_POINT"

# Handle different disk image formats
if echo "$IMG_TYPE" | grep -qi "qcow"; then
    echo "Detected: QCOW2 format"
    echo "Converting to NBD (Network Block Device)..."
    
    # Load nbd module
    modprobe nbd max_part=8 2>/dev/null || true
    
    # Find available nbd device
    NBD_DEV=""
    for i in {0..15}; do
        if [ ! -b /dev/nbd$i ]; then
            continue
        fi
        if ! lsblk /dev/nbd$i 2>/dev/null | grep -q nbd$i; then
            NBD_DEV="/dev/nbd$i"
            break
        fi
    done
    
    if [ -z "$NBD_DEV" ]; then
        echo "❌ No available NBD device found"
        echo "Try: sudo modprobe nbd max_part=16"
        exit 1
    fi
    
    echo "Using NBD device: $NBD_DEV"
    
    # Connect qcow2 to nbd
    qemu-nbd -c $NBD_DEV "$DISK_IMAGE"
    sleep 2
    
    # Try to find the partition
    PARTITION="${NBD_DEV}p1"
    if [ ! -b "$PARTITION" ]; then
        PARTITION="$NBD_DEV"
    fi
    
    echo "Mounting $PARTITION..."
    mount "$PARTITION" "$MOUNT_POINT"
    CLEANUP_CMD="umount $MOUNT_POINT && qemu-nbd -d $NBD_DEV"
    
elif echo "$IMG_TYPE" | grep -qi "partition\|filesystem\|ext"; then
    echo "Detected: Raw disk image or partition"
    echo "Mounting directly..."
    
    # Try direct mount first
    if mount -o loop "$DISK_IMAGE" "$MOUNT_POINT" 2>/dev/null; then
        echo "✓ Mounted successfully"
        CLEANUP_CMD="umount $MOUNT_POINT"
    else
        # Try with offset (for disk images with partition table)
        echo "Trying with partition offset..."
        
        # Get partition info
        OFFSET=$(fdisk -l "$DISK_IMAGE" 2>/dev/null | grep "^${DISK_IMAGE}1" | awk '{print $2}')
        
        if [ -n "$OFFSET" ]; then
            OFFSET_BYTES=$((OFFSET * 512))
            echo "Using offset: $OFFSET_BYTES bytes"
            mount -o loop,offset=$OFFSET_BYTES "$DISK_IMAGE" "$MOUNT_POINT"
            CLEANUP_CMD="umount $MOUNT_POINT"
        else
            echo "❌ Could not determine partition offset"
            rmdir "$MOUNT_POINT"
            exit 1
        fi
    fi
else
    echo "❌ Unknown disk image format"
    echo "Please convert to raw format first:"
    echo "  qemu-img convert -f qcow2 -O raw input.qcow2 output.img"
    rmdir "$MOUNT_POINT"
    exit 1
fi

echo "✓ Disk image mounted at: $MOUNT_POINT"
echo ""

# Create benchmark script
echo "Creating benchmark script..."
cat > "$MOUNT_POINT/benchmark_script.sh" << 'EOFSCRIPT'
#!/bin/sh

echo "=========================================="
echo "Racetrack Memory Benchmark Script"
echo "=========================================="
echo ""

# Phase 1: First exit (KVM -> O3 switch)
echo "Phase 1: Triggering CPU switch..."
/sbin/m5 exit || { echo "ERROR: m5 exit failed"; exit 1; }

# After switch
echo ""
echo "=========================================="
echo "Phase 2-3: Resumed on O3 CPU"
echo "=========================================="
echo ""

# Find NPB directory
NPB_DIR=""
for dir in /home/root/NPB /root/NPB /home/usr/NPB /usr/NPB; do
    if [ -d "$dir" ]; then
        NPB_DIR="$dir"
        echo "✓ Found NPB directory: $dir"
        break
    fi
done

if [ -z "$NPB_DIR" ]; then
    echo "❌ ERROR: NPB directory not found!"
    echo "Searching for NPB..."
    find / -name "*.S.x" 2>/dev/null | head -5
    /sbin/m5 exit
    exec /bin/sh
fi

cd "$NPB_DIR"
echo "Current directory: $(pwd)"
echo ""

# List available benchmarks
echo "Available benchmarks:"
if ls *.S.x 1> /dev/null 2>&1; then
    ls -lh *.S.x
    echo ""
else
    echo "❌ No *.S.x files found!"
    ls -la
    /sbin/m5 exit
    exec /bin/sh
fi

# Phase 4: ROI Measurement
echo "=========================================="
echo "Phase 4: ROI Measurement"
echo "=========================================="
echo ""

# Reset statistics
echo "Resetting statistics..."
/sbin/m5 resetstats
echo "✓ Statistics reset"
echo ""

# Run first benchmark (is.S.x is smallest)
echo "Running test benchmark: is.S.x"
echo "----------------------------------------"
if [ -f "is.S.x" ]; then
    echo "Executing is.S.x..."
    ./is.S.x || echo "WARNING: is.S.x failed or exited with error"
    echo ""
    echo "✓ is.S.x completed"
else
    # Try first available benchmark
    FIRST=$(ls *.S.x 2>/dev/null | head -1)
    if [ -n "$FIRST" ]; then
        echo "is.S.x not found, running $FIRST instead..."
        ./$FIRST || echo "WARNING: $FIRST failed"
        echo ""
        echo "✓ $FIRST completed"
    else
        echo "❌ No benchmarks available!"
        /sbin/m5 exit
        exec /bin/sh
    fi
fi

echo ""
echo "Dumping statistics..."
/sbin/m5 dumpstats
echo "✓ Statistics dumped"
echo ""

echo "=========================================="
echo "Benchmark Complete"
echo "=========================================="
echo ""

# Final exit
echo "Exiting simulation..."
/sbin/m5 exit

# Fallback shell
exec /bin/sh
EOFSCRIPT

chmod +x "$MOUNT_POINT/benchmark_script.sh"
echo "✓ Created /benchmark_script.sh"
echo ""

# Check for m5 binary
echo "Checking for m5 utility..."
if [ -f "$MOUNT_POINT/sbin/m5" ]; then
    echo "✓ /sbin/m5 exists"
    ls -lh "$MOUNT_POINT/sbin/m5"
else
    echo "⚠️  WARNING: /sbin/m5 not found!"
    echo ""
    echo "You need to copy m5 utility to the disk image:"
    echo "  1. Compile m5: cd ~/rm/gem5/util/m5 && scons build/x86/out/m5"
    echo "  2. Copy while mounted: cp build/x86/out/m5 $MOUNT_POINT/sbin/"
    echo ""
    read -p "Press Enter to continue or Ctrl+C to abort..."
fi
echo ""

# Check for NPB
echo "Checking for NPB benchmarks..."
FOUND_NPB=0
for dir in home/root/NPB root/NPB home/usr/NPB usr/NPB; do
    if [ -d "$MOUNT_POINT/$dir" ]; then
        echo "✓ Found NPB directory: /$dir"
        if ls "$MOUNT_POINT/$dir"/*.S.x 1> /dev/null 2>&1; then
            echo "  Benchmarks found:"
            ls -1 "$MOUNT_POINT/$dir"/*.S.x 2>/dev/null | head -5 | xargs -n1 basename
            FOUND_NPB=1
        else
            echo "  ⚠️  Directory exists but no *.S.x files found"
        fi
        break
    fi
done

if [ "$FOUND_NPB" -eq 0 ]; then
    echo "⚠️  WARNING: NPB benchmarks not found!"
    echo ""
    echo "You can copy NPB benchmarks while mounted:"
    echo "  mkdir -p $MOUNT_POINT/home/root/NPB"
    echo "  cp /path/to/NPB/*.S.x $MOUNT_POINT/home/root/NPB/"
    echo ""
    read -p "Press Enter to continue or Ctrl+C to abort..."
fi
echo ""

# Verify script
echo "Verifying benchmark script..."
if [ -f "$MOUNT_POINT/benchmark_script.sh" ]; then
    echo "✓ Script exists and is executable:"
    ls -lh "$MOUNT_POINT/benchmark_script.sh"
else
    echo "❌ ERROR: Script creation failed!"
    eval $CLEANUP_CMD
    rmdir "$MOUNT_POINT"
    exit 1
fi
echo ""

# Show script preview
echo "Script preview (first 30 lines):"
echo "----------------------------------------"
head -n 30 "$MOUNT_POINT/benchmark_script.sh"
echo "----------------------------------------"
echo ""

# Cleanup
echo "Cleaning up..."
eval $CLEANUP_CMD
sleep 1
rmdir "$MOUNT_POINT"
echo "✓ Unmounted and cleaned up"
echo ""

echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Copy fs_with_disk_script.py to ~/rm/gem5/configs/"
echo "  2. Update DISK_IMAGE path in the config if needed"
echo "  3. Run simulation:"
echo "     cd ~/rm/gem5"
echo "     ./build/X86/gem5.opt configs/fs_with_disk_script.py"
echo ""
echo "  4. Connect to console:"
echo "     telnet localhost 3456"
echo ""