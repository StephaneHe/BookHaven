package com.bookhaven.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.w3c.dom.Element
import java.io.File
import javax.xml.parsers.DocumentBuilderFactory

class ManifestSecurityTest {
    private val androidNs = "http://schemas.android.com/apk/res/android"

    /** Unit tests run with working dir = android/app; tolerate running from android/ too. */
    private val mainDir: File = listOf(File("src/main"), File("app/src/main"))
        .first { File(it, "AndroidManifest.xml").isFile }

    private fun application(): Element {
        val f = DocumentBuilderFactory.newInstance().apply { isNamespaceAware = true }
        val doc = f.newDocumentBuilder().parse(File(mainDir, "AndroidManifest.xml"))
        return doc.getElementsByTagName("application").item(0) as Element
    }

    @Test fun R97_allowBackupIsFalse() {
        assertEquals("false", application().getAttributeNS(androidNs, "allowBackup"))
    }

    @Test fun R97_networkSecurityConfigReferencedAndExists() {
        val ref = application().getAttributeNS(androidNs, "networkSecurityConfig")
        assertTrue("networkSecurityConfig must be an @xml/ resource, was '$ref'", ref.startsWith("@xml/"))
        val file = File(mainDir, "res/xml/${ref.removePrefix("@xml/")}.xml")
        assertTrue("referenced config $file must exist", file.isFile)
        val root = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(file).documentElement
        assertEquals("network-security-config", root.tagName)
    }

    @Test fun R97_noBlanketCleartextFlagInManifest() {
        // Cleartext is scoped in the network security config, not via the manifest flag.
        assertFalse(application().hasAttributeNS(androidNs, "usesCleartextTraffic"))
    }
}
