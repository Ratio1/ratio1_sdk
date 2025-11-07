"""
ex24_multi_video_stream_monitor.py
-----------------------------------

Deploy a pipeline that processes frames from multiple video streams and displays
stream metadata and statistics in real-time.

This tutorial demonstrates how to use the `MultiVideoStreamCv2` data capture thread
with the `MULTI_STREAM_FORWARDER` plugin to monitor multiple video sources and
receive metadata about each stream.

Usage:
  python ex24_multi_video_stream_monitor.py --node NODE_ADDRESS [OPTIONS]

Arguments:
  --node NODE_ADDRESS      Edge node address (required if multiple nodes, optional if single node)
  --sources JSON_STRING    JSON array of video sources (optional, uses defaults if not provided)
  --wait SECONDS          How long to run in seconds (default: 60)

Examples:
  # Use first available node and default test videos
  python ex24_multi_video_stream_monitor.py

  # Specify node address
  python ex24_multi_video_stream_monitor.py --node 0xai_ABC123DEF456...

  # Use custom video sources
  python ex24_multi_video_stream_monitor.py --node 0xai_ABC... --sources '[{"NAME":"camera1","URL":"rtsp://192.168.1.100/stream"}]'

  # Run for 5 minutes
  python ex24_multi_video_stream_monitor.py --node 0xai_ABC... --wait 300

Default Test Videos:
  - ForBiggerBlazes.mp4 (Google Cloud sample video)
  - ElephantsDream.mp4 (Google Cloud sample video)

Console Output:
  ======================================================================
  [DATA RECEIVED] 2025-11-07 12:15:57
  ======================================================================
  Streams processed: 1
  Total frames processed: 1
  Image in payload: True
    Image source: test_stream_2
    Image frame: 1
    Image size: 1280x720

    ✓ test_stream_1:
       Frame: 284 | Processed: 20
       Resolution: 720x1280 @ 23 fps
       Image shape: [720, 1280, 3]

    ✓ test_stream_2:
       Frame: 1 | Processed: 1
       Resolution: 720x1280 @ 24 fps
       Image shape: [720, 1280, 3]

  Stream counters: {'test_stream_1': 20, 'test_stream_2': 1}
  ======================================================================

What You'll See:
  - Real-time stream statistics
  - Frame counts and processing status
  - Stream resolution and FPS
  - Connection status for each stream
  - Image metadata (which stream, frame number, dimensions)
"""

import argparse
import json
import sys

from ratio1 import Payload, Pipeline, Session

# Default video sources
DEFAULT_SOURCES = [
    {
        'NAME': 'test_stream_1',
        'URL': 'http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4',
    },
    {
        'NAME': 'test_stream_2',
        'URL': 'http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4',
    },
]


def on_data(pipeline: Pipeline, payload: Payload):
    """Called when instance sends data"""
    # Get the custom data sent by the plugin
    data = payload.get("DATA", {})
    streams_processed = data.get('STREAMS_PROCESSED', 0)
    total_frames = data.get('TOTAL_FRAMES_PROCESSED', 0)
    stream_metadata = data.get('STREAM_METADATA', [])
    stream_counters = data.get('STREAM_COUNTERS', {})
    timestamp = data.get('TIMESTAMP', '')

    # Check if image is included in payload (SDK adds this automatically)
    has_image = payload.get('IMG_IN_PAYLOAD', False)

    print(f"\n{'='*70}")
    print(f"[DATA RECEIVED] {timestamp}")
    print(f"{'='*70}")
    print(f"Streams processed: {streams_processed}")
    print(f"Total frames processed: {total_frames}")
    print(f"Image in payload: {has_image}")

    # Display image info if present
    if has_image:
        img_stream_name = payload.get('_C_stream_name', 'unknown')
        img_frame_index = payload.get('_C_frame_current', 0)
        img_width = payload.get('IMG_ORIG_WIDTH', 0)
        img_height = payload.get('IMG_ORIG_HEIGHT', 0)
        print(f"  Image source: {img_stream_name}")
        print(f"  Image frame: {img_frame_index}")
        print(f"  Image size: {img_width}x{img_height}")

    print()

    for stream_info in stream_metadata:
        stream_name = stream_info.get('stream_name', 'unknown')
        frame_index = stream_info.get('frame_index', 0)
        processed_count = stream_info.get('processed_count', 0)
        resolution = stream_info.get('resolution', 'unknown')
        fps = stream_info.get('fps', 0)
        connected = stream_info.get('connected', False)
        image_shape = stream_info.get('image_shape', None)

        status = "✓" if connected else "✗"
        print(f"  {status} {stream_name}:")
        print(f"     Frame: {frame_index} | Processed: {processed_count}")
        print(f"     Resolution: {resolution} @ {fps} fps")
        print(f"     Image shape: {image_shape}")
        print()

    print(f"Stream counters: {stream_counters}")
    print(f"{'='*70}\n")


def on_notification(pipeline: Pipeline, notification: dict):
    """Called when instance sends a notification"""
    notif_type = notification.get('NOTIFICATION_TYPE', 'UNKNOWN')
    msg = notification.get('NOTIFICATION', '')
    print(f"[NOTIFICATION] {notif_type}: {msg}")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Multi-Stream Video Monitor - Display real-time statistics from multiple video streams',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use first available node and default test videos
  %(prog)s

  # Specify node address
  %(prog)s --node 0xai_ABC123DEF456...

  # Use custom video sources
  %(prog)s --node 0xai_ABC... --sources '[{"NAME":"camera1","URL":"rtsp://192.168.1.100/stream"}]'

  # Run for 5 minutes
  %(prog)s --node 0xai_ABC... --wait 300
        """
    )

    parser.add_argument(
        '--node',
        help='Edge node address (optional if only one node available)'
    )
    parser.add_argument(
        '--sources',
        help='JSON array of video sources (optional, uses default test videos if not provided)'
    )
    parser.add_argument(
        '--wait',
        type=int,
        default=60,
        help='How long to run in seconds (default: 60)'
    )

    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 70)
    print("Multi-Stream Video Monitor Tutorial")
    print("=" * 70)
    print()

    # Parse sources from command line or use defaults
    if args.sources:
        try:
            sources = json.loads(args.sources)
            if not isinstance(sources, list):
                print("ERROR: --sources must be a JSON array")
                sys.exit(1)
            print(f"Using sources from --sources argument")
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON in --sources: {e}")
            sys.exit(1)
    else:
        sources = DEFAULT_SOURCES
        print("Using default test video sources")

    print(f"\nConfiguration:")
    print(f"  Number of streams: {len(sources)}")
    print(f"  Run duration: {args.wait}s")
    print()
    print("Video sources:")
    for i, source in enumerate(sources, 1):
        name = source.get('NAME', f'stream_{i}')
        url = source.get('URL', 'no URL')
        print(f"  {i}. {name}")
        print(f"     URL: {url}")
    print()

    # Create session
    print("1. Creating session...")
    session = Session(encrypt_comms=True)

    # Wait for node
    print("2. Waiting for edge node...")
    try:
        session.wait_for_any_node()
    except Exception as e:
        print(f"ERROR: No node available - {e}")
        sys.exit(1)

    # Use provided node address or get first available
    if args.node:
        node = args.node
        print(f"   Using specified node: {node}")
    else:
        active_nodes = session.get_active_nodes()
        if active_nodes:
            node = active_nodes[0]
            print(f"   Using first available node: {node}")
        else:
            print("ERROR: No active nodes found")
            sys.exit(1)

    # Create pipeline
    print("3. Creating multi-stream pipeline...")
    pipeline = session.create_pipeline(
        node=node,
        name='multi_stream_capture',
        data_source='MultiVideoStreamCv2',
        config={
            'CAP_RESOLUTION': 5,
            'SOURCES': sources,
        },
    )

    # Create plugin instance
    print("4. Creating forwarder plugin instance...")
    instance = pipeline.create_plugin_instance(
        signature='MULTI_STREAM_FORWARDER',
        instance_id='image_saver',
        config={
            'PROCESS_DELAY': 3,
        },
        on_data=on_data,
        on_notification=on_notification,
    )

    # Deploy
    print("5. Deploying to node...")
    try:
        pipeline.deploy(with_confirmation=True, wait_confirmation=True, timeout=30)
    except Exception as e:
        print(f"ERROR: Deployment failed - {e}")
        session.close()
        sys.exit(1)

    print()
    print("=" * 70)
    print(f"DEPLOYED! Running for {args.wait} seconds...")
    print("=" * 70)
    print()
    print("Plugin will forward metadata from all streams every 3 seconds.")
    print("Watch for [DATA RECEIVED] messages below...")
    print()

    # Run
    try:
        session.run(wait=args.wait, close_pipelines=False, close_session=False)
    except KeyboardInterrupt:
        print("\nStopped by user")

    # Cleanup
    print("\nCleaning up...")
    pipeline.close()
    session.close()

    print("\nDone!")


if __name__ == '__main__':
    main()
