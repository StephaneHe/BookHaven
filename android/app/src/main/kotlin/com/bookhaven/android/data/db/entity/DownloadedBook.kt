package com.bookhaven.android.data.db.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "downloaded_books")
data class DownloadedBook(
    @PrimaryKey val bookId: Int,
    val title: String,
    val author: String,
    val format: String,
    val localPath: String,
    val downloadedAt: Long,
    val fileSize: Long,
    // Server content fingerprint at download time; used to detect a stale offline copy.
    val contentVersion: String = ""
)
