#!/bin/bash
# Disk Image Diagnostic Tool

echo "=========================================="
echo "Disk Image Diagnostic Tool"
echo "=========================================="
echo ""

echo "Searching for disk images..."
echo ""

# Search in common locations
echo "Checking /home/usr/rm/..."
find /home/usr/rm -name "*.img" -o -name "*.qcow2" -o -name "*.raw" 2>/dev/null | while read img; do
    echo ""
    echo "Found: $img"
    echo "  Size: $(du -h "$img" | cut -f1)"
    echo "  Type: $(file "$img" | cut -d: -f2)"
    
    # Try to get more info for qcow2
    if file "$img" | grep -qi qcow; then
        echo "  Format: QCOW2"
        if command -v qemu-img &> /dev/null; then
            echo "  Info:"
            qemu-img info "$img" | sed 's/^/    /'
        fi
    fi
done

echo ""
echo "Checking /home/usr/..."
find /home/usr -maxdepth 2 -name "*.img" -o -name "*.qcow2" -o -name "*.raw" 2>/dev/null | while read img; do
    echo ""
    echo "Found: $img"
    echo "  Size: $(du -h "$img" | cut -f1)"
    echo "  Type: $(file "$img" | cut -d: -f2)"
done

echo ""
echo "=========================================="
echo "Please provide the correct disk image path"
echo "=========================================="
echo ""
echo "Enter the full path to your disk image:"
read -p "> " DISK_PATH

if [ -z "$DISK_PATH" ]; then
    echo "No path provided"
    exit 1
fi

if [ ! -f "$DISK_PATH" ]; then
    echo "❌ File not found: $DISK_PATH"
    exit 1
fi

echo ""
echo "Analyzing: $DISK_PATH"
echo ""

# File type
echo "File type:"
file "$DISK_PATH"
echo ""

# If qcow2, show more info
if file "$DISK_PATH" | grep -qi qcow; then
    echo "QCOW2 image detected"
    echo ""
    
    if command -v qemu-img &> /dev/null; then
        echo "Image info:"
        qemu-img info "$DISK_PATH"
        echo ""
    fi
    
    echo "To use this image with the setup script:"
    echo "  1. Option A - Use NBD (recommended):"
    echo "     The smart_disksetup.sh script will handle this automatically"
    echo ""
    echo "  2. Option B - Convert to raw:"
    echo "     qemu-img convert -f qcow2 -O raw \\"
    echo "       \"$DISK_PATH\" \\"
    echo "       \"${DISK_PATH%.qcow2}.raw\""
    echo ""
else
    echo "Attempting to analyze partition structure..."
    fdisk -l "$DISK_PATH" 2>/dev/null || echo "Not a partitioned disk image"
    echo ""
    
    echo "Attempting direct mount (read-only test)..."
    TEMP_MOUNT="/tmp/test_mount_$$"
    mkdir -p "$TEMP_MOUNT"
    
    if sudo mount -o loop,ro "$DISK_PATH" "$TEMP_MOUNT" 2>/dev/null; then
        echo "✓ Direct mount successful!"
        echo ""
        echo "Root directory contents:"
        ls -la "$TEMP_MOUNT" | head -20
        echo ""
        
        # Check for m5
        if [ -f "$TEMP_MOUNT/sbin/m5" ]; then
            echo "✓ /sbin/m5 found"
        else
            echo "⚠️  /sbin/m5 not found"
        fi
        
        # Check for NPB
        for dir in home/root/NPB root/NPB home/usr/NPB; do
            if [ -d "$TEMP_MOUNT/$dir" ]; then
                echo "✓ NPB found at: /$dir"
                ls "$TEMP_MOUNT/$dir" | head -5
                break
            fi
        done
        
        sudo umount "$TEMP_MOUNT"
        rmdir "$TEMP_MOUNT"
        
        echo ""
        echo "✅ This disk image can be used directly with smart_disksetup.sh"
    else
        echo "❌ Direct mount failed, trying with offset..."
        
        # Try to find partition offset
        OFFSET=$(fdisk -l "$DISK_PATH" 2>/dev/null | grep "^${DISK_PATH}1" | awk '{print $2}')
        
        if [ -n "$OFFSET" ]; then
            OFFSET_BYTES=$((OFFSET * 512))
            echo "Found partition at offset: $OFFSET sectors ($OFFSET_BYTES bytes)"
            
            if sudo mount -o loop,offset=$OFFSET_BYTES,ro "$DISK_PATH" "$TEMP_MOUNT" 2>/dev/null; then
                echo "✓ Mount with offset successful!"
                sudo umount "$TEMP_MOUNT"
                rmdir "$TEMP_MOUNT"
                echo ""
                echo "✅ This disk image needs offset mounting"
                echo "   smart_disksetup.sh will handle this automatically"
            else
                echo "❌ Mount with offset also failed"
                rmdir "$TEMP_MOUNT"
            fi
        else
            rmdir "$TEMP_MOUNT"
            echo "❌ Could not determine partition structure"
        fi
    fi
fi

echo ""
echo "=========================================="
echo "Recommended Action"
echo "=========================================="
echo ""
echo "Run the smart disk setup script:"
echo "  sudo bash smart_disksetup.sh"
echo ""
echo "It will automatically handle your disk image format"
echo ""