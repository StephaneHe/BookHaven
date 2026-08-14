package com.bookhaven.android.di

import android.content.Context
import androidx.room.Room
import com.bookhaven.android.data.db.AppDatabase
import com.bookhaven.android.data.db.dao.CachedBookDao
import com.bookhaven.android.data.db.dao.DownloadedBookDao
import com.bookhaven.android.data.db.dao.ReadingProgressDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext ctx: Context): AppDatabase =
        Room.databaseBuilder(ctx, AppDatabase::class.java, "bookhaven.db")
            .addMigrations(AppDatabase.MIGRATION_1_2, AppDatabase.MIGRATION_2_3, AppDatabase.MIGRATION_3_4)
            .build()

    @Provides
    fun provideDownloadedBookDao(db: AppDatabase): DownloadedBookDao =
        db.downloadedBookDao()

    @Provides
    fun provideReadingProgressDao(db: AppDatabase): ReadingProgressDao =
        db.readingProgressDao()

    @Provides
    fun provideCachedBookDao(db: AppDatabase): CachedBookDao =
        db.cachedBookDao()
}
