package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.runBlocking
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okio.Buffer
import java.io.File
import java.security.Permission

/** Compiled alongside the unchanged mobile adapter, with no Gradle or sockets.
 * This checks byte reading and deserialization, not TLS or device acceptance.
 */
@Suppress("DEPRECATION", "OVERRIDE_DEPRECATION")
fun main(args: Array<String>) {
    check(System.getProperty("java.specification.version") == "17")
    System.setSecurityManager(object : SecurityManager() {
        override fun checkPermission(permission: Permission) = Unit
        override fun checkConnect(host: String?, port: Int) = error("Network forbidden")
        override fun checkListen(port: Int) = error("Listeners forbidden")
        override fun checkAccept(host: String?, port: Int) = error("Network forbidden")
    })
    var payload = byteArrayOf()
    var knownLength = true
    var intercepted = 0
    val client = OkHttpClient.Builder().addInterceptor { chain ->
        check(chain.request().url.host == "photohouse.test")
        check(chain.request().url.encodedPath == "/assets/101/captions")
        check(chain.request().url.query == "library=family-a")
        intercepted++
        val bytes = payload
        val body = object : ResponseBody() {
            private val buffer = Buffer().write(bytes)
            override fun contentType() = "application/json".toMediaType()
            override fun contentLength() = if (knownLength) bytes.size.toLong() else -1L
            override fun source() = buffer
        }
        Response.Builder().request(chain.request()).protocol(Protocol.HTTP_1_1)
            .code(200).message("Synthetic").header("Content-Type", "application/json")
            .body(body).build()
    }.build()
    try {
        val api = HttpsPhotoHouseApi(TrustedOrigin.parse("https://photohouse.test"), client)
        val token = Bearer.from(SessionToken(86400L, "S".repeat(43), "Bearer"))
        runBlocking {
            for (length in listOf(true, false)) {
                knownLength = length
                for ((name, count) in listOf("small" to 1, "unicode" to 15,
                    "escaped" to 10, "truncated" to 15, "empty" to 0, "exact" to 14)) {
                    payload = File(args.single(), "$name.json").readBytes()
                    check(payload.size <= HttpsPhotoHouseApi.JSON_LIMIT)
                    val result = api.captions(token, "family-a", "101")
                    check(result.library_id == "family-a" && result.asset_id == "101")
                    check(result.items.size == count)
                    check(result.has_more == (name in listOf("unicode", "escaped", "truncated")))
                    check(result.items.all { it.truncated == (name == "truncated") })
                    when (name) {
                        "small" -> check(result.items.single().text == "caption-101")
                        "unicode", "truncated" -> check(result.items.all { it.text == "\uD83D\uDFE6".repeat(8192) })
                        "escaped" -> check(result.items.all { it.text == "\u0001".repeat(8192) })
                        "exact" -> check(payload.size == HttpsPhotoHouseApi.JSON_LIMIT)
                    }
                }
                payload = File(args.single(), "oversized.json").readBytes()
                check(payload.size == HttpsPhotoHouseApi.JSON_LIMIT + 1)
                val failure = runCatching { api.captions(token, "family-a", "101") }.exceptionOrNull()
                check(failure is ApiFailure && failure.kind == FailureKind.TOO_LARGE)
            }
        }
        check(intercepted == 14)
        println("PASS 14 Kotlin adapter cases: known/unknown length, UTF-8, escaping, exact limit and oversize rejection; no sockets")
    } finally {
        client.dispatcher.executorService.shutdown()
        client.connectionPool.evictAll()
    }
}
