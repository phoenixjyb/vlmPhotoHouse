#!/usr/bin/env python3
"""Replay synthetic ASGI captions through the actual Kotlin adapter without sockets.

Requires explicitly selected mobile source, Java 17 and existing Gradle Maven cache.
No Gradle daemon, dependency resolution/download, mobile edits or installed artifacts.
Compile current mobile sources and a small backend-owned test into a temporary dir.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    'android/protocol/src/main/kotlin/dev/photohouse/protocol/WireModels.kt',
    'android/live-core/src/main/kotlin/dev/photohouse/connected/core/PhotoHouseApi.kt',
    'android/live-core/src/main/kotlin/dev/photohouse/connected/core/HttpsPhotoHouseApi.kt',
)
COMPILER = (
    ('org.jetbrains.kotlin', 'kotlin-compiler-embeddable', '1.9.24'),
    ('org.jetbrains.kotlin', 'kotlin-stdlib', '1.9.24'),
    ('org.jetbrains.kotlin', 'kotlin-script-runtime', '1.9.24'),
    ('org.jetbrains.kotlin', 'kotlin-reflect', '1.6.10'),
    ('org.jetbrains.intellij.deps', 'trove4j', '1.0.20200330'),
    ('org.jetbrains', 'annotations', '13.0'),
)
RUNTIME = (
    ('org.jetbrains.kotlin', 'kotlin-stdlib', '1.9.24'),
    ('org.jetbrains', 'annotations', '13.0'),
    ('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm', '1.8.1'),
    ('org.jetbrains.kotlinx', 'kotlinx-serialization-core-jvm', '1.6.3'),
    ('org.jetbrains.kotlinx', 'kotlinx-serialization-json-jvm', '1.6.3'),
    ('com.squareup.okhttp3', 'okhttp', '4.12.0'),
    ('com.squareup.okio', 'okio-jvm', '3.6.0'),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mobile-root', type=Path, required=True)
    parser.add_argument('--java', type=Path, required=True)
    parser.add_argument('--maven-cache', type=Path, required=True)
    parser.add_argument('--evidence-output', type=Path, required=True)
    args = parser.parse_args()
    mobile = args.mobile_root.resolve()
    hashes = {}
    def jar(coordinate):
        group, artifact, version = coordinate
        matches = list((args.maven_cache/group/artifact/version).glob(f'*/{artifact}-{version}.jar'))
        assert len(matches) == 1, 'Required cached dependency missing or ambiguous: '+artifact
        data = matches[0].read_bytes()
        assert hashlib.sha1(data).hexdigest() == matches[0].parent.name.zfill(40), 'Cache checksum mismatch: '+artifact
        hashes[':'.join(coordinate)] = hashlib.sha256(data).hexdigest()
        return str(matches[0])
    compiler = os.pathsep.join(map(jar, COMPILER))
    runtime = os.pathsep.join(map(jar, RUNTIME))
    plugin = jar(('org.jetbrains.kotlin', 'kotlin-serialization-compiler-plugin-embeddable', '1.9.24'))
    sources = {}
    for name in SOURCES:
        data = (mobile/name).read_bytes()
        committed = subprocess.check_output(['git','show','HEAD:'+name], cwd=mobile)
        assert data == committed, 'Selected mobile source is dirty'
        sources[name] = hashlib.sha256(data).hexdigest()
    with tempfile.TemporaryDirectory(prefix='photohouse-caption-kotlin-') as directory:
        temporary = Path(directory)
        result = subprocess.run([sys.executable, str(ROOT/'scripts/android_readiness_probe.py'),
            '--mobile-root',str(mobile),'--candidate','--caption-output',str(temporary/'captions')],
            check=True, capture_output=True, text=True)
        report = json.loads(result.stdout)
        output = temporary/'classes'
        subprocess.run([str(args.java), '-cp',compiler,'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
            '-no-stdlib','-no-reflect','-jvm-target','17','-classpath',runtime,
            '-Xplugin='+plugin,'-d',str(output),*[str(mobile/name) for name in SOURCES],
            str(ROOT/'tests/security/android/CaptionBudgetCheck.kt')], check=True)
        test = subprocess.run([str(args.java),'-cp',str(output)+os.pathsep+runtime,
            'dev.photohouse.connected.core.CaptionBudgetCheckKt',str(temporary/'captions')],
            check=True, capture_output=True, text=True, timeout=60)
        report.update(kotlin_adapter_cases=14, kotlin_adapter_result=test.stdout.strip(),
            kotlin_mobile_source_sha256=sources, kotlin_dependency_sha256=hashes,
            kotlin_transport='in_memory_interceptor_with_network_denied',
            kotlin_tls_checked=False, mobile_modified=False, consumer_repin_completed=False)
        args.evidence_output.write_text(json.dumps(report,indent=2)+'\n')
        print(test.stdout.strip())


if __name__ == '__main__':
    main()
